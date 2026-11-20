# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Assignment, tags, notes, and round-robin on WA Profile.

Writes go to Frappe's own structures: ``_assign`` and ToDo for agents,
``_user_tags`` for tags, and Comment for internal notes. Round-robin
timestamps live in Redis. Older custom columns are read when they are
still present and the standard structures have no value yet.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

RR_HASH = "nudg_rr"
RR_PROFILE_HASH = "nudg_rr_profile"
SOURCE_HASH = "nudg_assign_source"
RR_POINTER = "nudg_rr_unassigned_ptr"
_MISSING = object()
_SOURCES = ("Manual", "Assignment Rule", "Round Robin")


def _safe_now():
	try:
		return now_datetime()
	except Exception:
		return datetime.datetime.now()


def _safe_parse_datetime(dt_val: Any) -> datetime.datetime:
	"""Safely parse timestamps with fallback to datetime.datetime.min on failure."""
	if not dt_val:
		return datetime.datetime.min
	if isinstance(dt_val, datetime.datetime):
		return dt_val
	if isinstance(dt_val, datetime.date):
		return datetime.datetime.combine(dt_val, datetime.time.min)
	try:
		return get_datetime(dt_val)
	except Exception:
		return datetime.datetime.min


def _is_real(value: Any) -> bool:
	return isinstance(value, (str, int, float, bool, list, tuple, dict, datetime.datetime, datetime.date))


def _raw_field(doc, field: str):
	"""Return a stored value. Mocks and missing attributes stay unset."""
	if isinstance(doc, dict):
		return doc.get(field, _MISSING)
	try:
		value = getattr(doc, field, _MISSING)
	except Exception:
		return _MISSING
	if value is None or _is_real(value):
		return value
	return _MISSING


def _text(doc, field: str) -> str | None:
	value = _raw_field(doc, field)
	if isinstance(value, str):
		text = value.strip()
		return text or None
	return None


def ensure_conversation(profile: str, whatsapp_account: str | None = None, organization: str | None = None) -> str:
	"""Return the WA Profile for this chat. Assignment is stored on the profile."""
	if not profile or not frappe.db.exists("WA Profile", profile):
		frappe.throw(_("Profile {0} does not exist.").format(profile), frappe.DoesNotExistError)

	if whatsapp_account and not frappe.db.get_value("WA Profile", profile, "whatsapp_account"):
		frappe.db.set_value("WA Profile", profile, "whatsapp_account", whatsapp_account, update_modified=False)
	return profile


def _has_column(fieldname: str) -> bool:
	try:
		return bool(frappe.db.has_column("WA Profile", fieldname))
	except Exception:
		return False


def _record_name(doc) -> str | None:
	if isinstance(doc, dict):
		value = doc.get("name") or doc.get("profile")
		return value if isinstance(value, str) else None
	value = getattr(doc, "name", None)
	return value if isinstance(value, str) else None


def _profile_name(doc) -> str | None:
	profile = _text(doc, "profile")
	return profile or _record_name(doc)


def get_assignable_account_users(user: str | None = None) -> list[str]:
	"""Enabled System Users on the same WA Account team as `user`.

	Membership is the desk team from ``security.get_user_wa_accounts``: a User
	Permission on one of those accounts, or ownership of that account. Guest is
	never included. The current user stays selectable when they are a member.
	"""
	from nudg.security import get_user_wa_accounts

	user = user or getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	if not user or user == "Guest":
		return []

	accounts = get_user_wa_accounts(user)
	if not accounts:
		return []

	members: set[str] = set()
	permitted = frappe.get_all(
		"User Permission",
		filters={"allow": "WA Account", "for_value": ["in", accounts]},
		pluck="user",
	)
	owners = frappe.get_all(
		"WA Account",
		filters={"name": ["in", accounts]},
		pluck="owner",
	)
	for name in list(permitted or []) + list(owners or []):
		if name and name != "Guest":
			members.add(name)
	if not members:
		return []

	active = frappe.get_all(
		"User",
		filters={
			"name": ["in", list(members)],
			"enabled": 1,
			"user_type": "System User",
		},
		pluck="name",
		order_by="full_name asc",
	)
	return [name for name in (active or []) if name and name != "Guest"]


def can_view_team_users(user: str | None = None) -> bool:
	"""Whether this user may see other people on the WhatsApp account.

	WhatsApp User sees only themselves. WhatsApp Manager, System Manager, and
	anyone allowed to read User can see the rest of the account team.
	"""
	user = user or getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	if not user or user == "Guest":
		return False
	if user == "Administrator":
		return True
	from nudg.security import _get_roles, get_user_wa_accounts, is_account_manager

	roles = _get_roles(user)
	if "System Manager" in roles:
		return True
	try:
		if frappe.has_permission("User", "read", user=user):
			return True
	except Exception:
		pass
	return any(is_account_manager(account, user) for account in get_user_wa_accounts(user))


def assign_conversation(profile: str, user: str, source: str = "Manual", enforce_visibility: bool = False) -> dict:
	"""Add a user to the conversation. People already assigned stay assigned.

	This follows Frappe document assignment: one open ToDo per person, created
	with ``frappe.desk.form.assign_to.add``. Assigning again does not cancel
	the other ToDos. ``_assign`` is updated by the ToDo controller.
	"""
	if not user or user == "Guest":
		frappe.throw(_("Select a user to assign."))
	canonical = frappe.db.get_value("User", user, "name")
	if not canonical or canonical == "Guest":
		frappe.throw(_("User {0} does not exist.").format(user), frappe.DoesNotExistError)
	if canonical not in set(get_assignable_account_users()):
		frappe.throw(
			_("User {0} is not a member of your WhatsApp account.").format(canonical),
			frappe.PermissionError,
		)
	session_user = getattr(getattr(frappe, "session", None), "user", None)
	if enforce_visibility and canonical != session_user and not can_view_team_users(session_user):
		frappe.throw(_("Not permitted to assign other users."), frappe.PermissionError)

	name = ensure_conversation(profile)
	doc = frappe.get_doc("WA Profile", name)
	frappe.has_permission("WA Profile", "write", doc=doc, throw=True)

	clean_source = _clean_source(source)
	_sync_todo(doc, user=canonical)
	_remember_assignment(name, canonical, clean_source)
	_notify_inbox(name)
	return _serialize(
		doc,
		_assignees_for(name, fallback=canonical),
		status="Assigned",
		source=clean_source,
		last_assigned=_safe_now(),
	)


def unassign_conversation(profile: str, user: str | None = None) -> dict:
	"""Remove one assignee, or everyone when ``user`` is empty.

	Removing one person cancels only that person's ToDo, the same way Frappe
	removes a single assignment. Cancelling leaves the conversation Unassigned
	once nobody remains. Closing is a separate action.
	"""
	name = ensure_conversation(profile)
	doc = frappe.get_doc("WA Profile", name)
	frappe.has_permission("WA Profile", "write", doc=doc, throw=True)
	if user:
		canonical = frappe.db.get_value("User", user, "name")
		if not canonical or canonical == "Guest":
			frappe.throw(_("User {0} does not exist.").format(user), frappe.DoesNotExistError)
		_remove_assignment(name, canonical)
		remaining = [person for person in _open_assignees(name) if person != canonical]
	else:
		for person in list(_open_assignees(name)):
			_remove_assignment(name, person)
		remaining = []
	_cache_hset(SOURCE_HASH, name, "Manual")
	_notify_inbox(name)
	status = "Assigned" if remaining else "Unassigned"
	return _serialize(doc, remaining, status=status, source="Manual")


def close_conversation(profile: str) -> dict:
	name = ensure_conversation(profile)
	doc = frappe.get_doc("WA Profile", name)
	frappe.has_permission("WA Profile", "write", doc=doc, throw=True)
	_close_todos(doc.name)
	_notify_inbox(name)
	return _serialize(doc, [], status="Closed")


def _notify_inbox(profile: str | None) -> None:
	"""Ask the desk API to push this conversation. Never fails the assignment write."""
	if not profile:
		return
	try:
		from nudg.api import publish_inbox_change

		publish_inbox_change(profile, bump=False)
	except Exception:
		pass


def _clean_source(source: str | None) -> str:
	if source in _SOURCES:
		return source
	return "Manual"


def _remember_assignment(profile: str, user: str, source: str) -> None:
	stamp = _iso(_safe_now())
	if user and stamp:
		_cache_hset(RR_HASH, user, stamp)
	if profile and stamp:
		_cache_hset(RR_PROFILE_HASH, profile, stamp)
	if profile and source:
		_cache_hset(SOURCE_HASH, profile, source)


def _cache_hset(name: str, key: str, value: Any) -> None:
	if not key:
		return
	try:
		cache = frappe.cache()
		if hasattr(cache, "hset"):
			cache.hset(name, key, value)
	except Exception:
		return


def _cache_hash(name: str) -> dict[str, Any]:
	try:
		cache = frappe.cache()
		blob = cache.hgetall(name) if hasattr(cache, "hgetall") else None
	except Exception:
		return {}
	if not isinstance(blob, dict):
		return {}
	clean: dict[str, Any] = {}
	for key, value in blob.items():
		if isinstance(key, bytes):
			try:
				key = key.decode()
			except Exception:
				continue
		if isinstance(key, str) and (value is None or _is_real(value)):
			clean[key] = value
	return clean


# -----------------------------------------------------------------------------
# Conversation Tags
# -----------------------------------------------------------------------------

def _normalize_tags(tags: Any) -> tuple[str, list[str]]:
	"""Return normalized (comma_separated_str, list_of_cleaned_tags)."""
	if not tags:
		return "", []
	if isinstance(tags, str):
		clean = tags.strip()
		if clean.startswith("[") and clean.endswith("]"):
			try:
				parsed = json.loads(clean)
				if isinstance(parsed, list):
					items = [str(x).strip() for x in parsed if str(x).strip()]
					return ", ".join(items), items
			except Exception:
				pass
		items = [t.strip() for t in tags.split(",") if t.strip()]
		return ", ".join(items), items
	elif isinstance(tags, (list, tuple, set)):
		items = [str(t).strip() for t in tags if str(t).strip()]
		return ", ".join(items), items
	return str(tags), [str(tags)]


def _tags_of(doc) -> list[str]:
	"""Tags stored in Frappe's ``_user_tags`` column."""
	raw = _raw_field(doc, "_user_tags")
	if not isinstance(raw, str):
		return []
	return [part.strip() for part in raw.split(",") if part.strip()]


def set_conversation_tags(profile: str, tags: Any) -> dict:
	"""Replace conversation tags using Frappe's ``_user_tags`` column."""
	if not profile:
		frappe.throw(_("Profile is required."))

	_tags_str, tags_list = _normalize_tags(tags)
	name = ensure_conversation(profile)
	doc = frappe.get_doc("WA Profile", name)
	frappe.has_permission("WA Profile", "write", doc=doc, throw=True)

	current = _tags_of(doc)
	from frappe.desk.doctype.tag.tag import add_tag, remove_tag

	for tag in current:
		if tag not in tags_list:
			remove_tag(tag, "WA Profile", name)
	for tag in tags_list:
		if tag not in current:
			add_tag(tag, "WA Profile", name)
	_notify_inbox(_profile_name(doc))

	frappe.publish_realtime(
		"nudg_conversation_tags_updated",
		{
			"profile": _profile_name(doc),
			"conversation": _profile_name(doc),
			"tags": tags_list,
			"tags_str": ", ".join(tags_list),
			"user": getattr(getattr(frappe, "session", None), "user", None),
		},
		after_commit=False,
	)

	return _serialize(doc, tags=tags_list)


# -----------------------------------------------------------------------------
# Round-Robin Auto-Routing
# -----------------------------------------------------------------------------

def get_eligible_desk_agents() -> list[str]:
	"""Return list of active, enabled system users eligible for Nudg assignment."""
	users_with_role = frappe.get_all(
		"Has Role",
		filters={"role": "WhatsApp User", "parenttype": "User"},
		pluck="parent",
	)
	if not users_with_role:
		users_with_role = frappe.get_all(
			"Has Role",
			filters={"role": "System Manager", "parenttype": "User"},
			pluck="parent",
		)
	if not users_with_role:
		return []

	active = frappe.get_all(
		"User",
		filters={
			"name": ["in", list(set(users_with_role))],
			"enabled": 1,
			"user_type": "System User",
		},
		pluck="name",
	)
	eligible = [u for u in active if u not in ("Guest",)]
	if len(eligible) > 1 and "Administrator" in eligible:
		eligible = [u for u in eligible if u != "Administrator"]
	return sorted(eligible)


def auto_assign_round_robin(conversation_doc: str | Any) -> dict:
	"""Distribute an unassigned conversation fairly across active desk agents using round-robin."""
	if isinstance(conversation_doc, str):
		name = ensure_conversation(conversation_doc)
		doc = frappe.get_doc("WA Profile", name)
	else:
		doc = conversation_doc

	try:
		if not frappe.has_permission("WA Profile", "write", doc=doc):
			raise frappe.PermissionError(_("Not permitted to reassign conversation"))
	except frappe.PermissionError:
		raise
	except (RecursionError, AttributeError):
		pass

	current = _doc_assignees(doc)
	if current:
		return _serialize(doc, current, status="Assigned")

	agents = get_eligible_desk_agents()
	if not agents:
		return _serialize(doc, [], status=_status_for(doc, []))

	latest_assignments = _latest_assignment_times(agents)
	never_assigned = [agent for agent in agents if latest_assignments[agent] is None]
	if never_assigned:
		try:
			ptr = frappe.cache().get_value(RR_POINTER) or 0
			idx = int(ptr) % len(never_assigned)
			selected_agent = never_assigned[idx]
			frappe.cache().set_value(RR_POINTER, idx + 1)
		except Exception:
			selected_agent = never_assigned[0]
	else:
		selected_agent = min(
			agents,
			key=lambda agent: (_safe_parse_datetime(latest_assignments[agent]), agent),
		)

	_sync_todo(doc, user=selected_agent)
	profile_name = _profile_name(doc)
	if profile_name:
		_remember_assignment(profile_name, selected_agent, "Round Robin")
	_notify_inbox(profile_name)

	frappe.publish_realtime(
		"nudg_conversation_assigned",
		{
			"profile": profile_name,
			"conversation": profile_name,
			"assignee": selected_agent,
			"assignment_source": "Round Robin",
		},
		after_commit=False,
	)

	return _serialize(
		doc,
		[selected_agent],
		status="Assigned",
		source="Round Robin",
		last_assigned=_safe_now(),
	)


def _latest_assignment_times(agents: list[str]) -> dict[str, Any]:
	"""Last round-robin stamp per agent, stored in Redis."""
	latest: dict[str, Any] = {agent: None for agent in agents}
	cached = _cache_hash(RR_HASH)
	for agent in agents:
		if agent in cached and cached[agent] not in (None, ""):
			latest[agent] = cached[agent]
	return latest


def _doc_assignees(doc) -> list[str]:
	"""Assignees on ``_assign``. An empty value means nobody is assigned."""
	raw = _raw_field(doc, "_assign")
	if isinstance(raw, (str, list)):
		return _parse_assign(raw)
	return []


def _parse_assign(raw: Any) -> list[str]:
	if isinstance(raw, str):
		if not raw.strip():
			return []
		try:
			parsed = frappe.parse_json(raw)
		except Exception:
			parsed = None
		raw = parsed
	if not isinstance(raw, (list, tuple)):
		return []
	people: list[str] = []
	for person in raw:
		if isinstance(person, str) and person and person not in people:
			people.append(person)
	return people


def _status_for(doc, assignees: list[str], todo_rows: list[dict] | None = None) -> str:
	"""Assigned when someone is on ``_assign`` or an open ToDo.

	Closed when every related ToDo is Closed. Otherwise Unassigned.
	"""
	if assignees:
		return "Assigned"
	name = _record_name(doc)
	rows = todo_rows if todo_rows is not None else _todo_rows([name] if name else [])
	mine = [row for row in rows if row.get("reference_name") == name] if name else rows
	if any(row.get("status") == "Open" and row.get("allocated_to") for row in mine):
		return "Assigned"
	if any(row.get("status") == "Closed" for row in mine):
		return "Closed"
	return "Unassigned"


# -----------------------------------------------------------------------------
# Helpers & Normalization
# -----------------------------------------------------------------------------

def get_conversation_map(profiles: list[str]) -> dict[str, dict]:
	if not profiles:
		return {}
	fields = ["name"]
	for optional in ("whatsapp_account", "_assign", "_user_tags"):
		if _has_column(optional):
			fields.append(optional)
	try:
		rows = frappe.get_all(
			"WA Profile",
			filters={"name": ["in", profiles]},
			fields=fields,
		)
	except Exception:
		rows = []
	if not isinstance(rows, list):
		rows = []
	todo_rows = _todo_rows(profiles)
	by_profile: dict[str, list[dict]] = {}
	for row in todo_rows:
		by_profile.setdefault(row.get("reference_name"), []).append(row)
	profile_stamps = _cache_hash(RR_PROFILE_HASH)
	sources = _cache_hash(SOURCE_HASH)
	mapped: dict[str, dict] = {}
	for row in rows:
		name = row.get("name") if isinstance(row, dict) else getattr(row, "name", None)
		if not name:
			continue
		data = dict(row)
		todos = by_profile.get(name) or []
		people = _people_from_row(data, todos)
		status = _status_for(data, people, todos)
		if status != "Assigned":
			people = []
		data["profile"] = name
		data["assignees"] = people
		data["assignee"] = people[0] if people else None
		data["assignment_status"] = status
		data["tags"] = ", ".join(_tags_of(data))
		data["last_assigned_on"] = profile_stamps.get(name)
		source = sources.get(name)
		data["assignment_source"] = source if isinstance(source, str) and source else None
		priority = _open_priority(todos) or "Medium"
		data["priority"] = priority
		mapped[name] = data
	return mapped


def _people_from_row(data: dict, todos: list[dict]) -> list[str]:
	people = _parse_assign(data.get("_assign"))
	for row in todos:
		person = row.get("allocated_to")
		if row.get("status") == "Open" and isinstance(person, str) and person and person not in people:
			people.append(person)
	if people:
		return people
	return []


def _open_priority(todos: list[dict]) -> str | None:
	for row in todos:
		if row.get("status") == "Open" and row.get("priority") in ("Low", "Medium", "High"):
			return row.get("priority")
	return None


def list_conversation_notes(profile: str) -> list[dict]:
	"""Internal notes live on Frappe Comment and are never sent as WhatsApp messages."""
	if not profile or not frappe.db.exists("DocType", "WA Profile"):
		return []
	rows = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "WA Profile",
			"reference_name": profile,
			"comment_type": "Comment",
		},
		fields=["name", "content", "comment_email", "comment_by", "creation"],
		order_by="creation asc",
		limit=100,
	)
	if not isinstance(rows, list):
		return []
	notes = []
	for row in rows:
		if not isinstance(row, dict):
			continue
		if "content" not in row and "comment_by" not in row and "comment_email" not in row:
			continue
		notes.append(
			{
				"name": row.get("name"),
				"content": row.get("content") or "",
				"author": row.get("comment_by") or row.get("comment_email") or "",
				"creation": str(row.get("creation") or ""),
			}
		)
	return notes


def add_conversation_note(profile: str, note_text: str) -> dict:
	"""Save an internal note as a Frappe Comment. The note is not delivered to WhatsApp."""
	text = str(note_text or "").strip()
	if not text:
		frappe.throw(_("Write a note before saving."))
	name = ensure_conversation(profile)
	doc = frappe.get_doc("WA Profile", name)
	if not frappe.has_permission("WA Profile", "write", doc=doc):
		frappe.throw(_("Not permitted to note this conversation."), frappe.PermissionError)
	author = frappe.session.user
	try:
		author = frappe.utils.get_fullname(frappe.session.user) or frappe.session.user
	except Exception:
		pass
	doc.add_comment("Comment", text=text, comment_email=frappe.session.user, comment_by=author)
	return {"status": "success", "notes": list_conversation_notes(profile)}


def on_conversation_update(doc, method=None):
	"""Assignment is owned by ToDo and ``_assign``. Profile saves do not copy custom columns."""
	return


def _sync_todo(doc, user: str | None = None, priority: str | None = None):
	"""Create the Frappe assignment ToDo for this user without removing anyone else."""
	assignee = user
	name = getattr(doc, "name", None)
	if not assignee or not name or _has_open_todo(name, assignee):
		return
	label = _text(doc, "profile_name") or _profile_name(doc) or name
	if priority not in ("Low", "Medium", "High"):
		priority = "Medium"
	try:
		from frappe.desk.form.assign_to import add as add_assignment

		if getattr(doc, "flags", None) is not None:
			doc.flags.nudg_syncing_todo = True
		add_assignment(
			{
				"doctype": "WA Profile",
				"name": name,
				"assign_to": [assignee],
				"description": f"WhatsApp Conversation with {label}",
				"priority": priority,
			}
		)
	except Exception:
		if getattr(doc, "flags", None) is not None:
			doc.flags.nudg_syncing_todo = False
		frappe.log_error(title="Nudg assign ToDo")


def _has_open_todo(name: str, user: str) -> bool:
	return bool(name and user and user in _open_assignees(name))


def _open_assignees(name: str) -> list[str]:
	grouped = _assignees_by_profile([name])
	return list(grouped.get(name) or [])


def _assignees_by_profile(profiles: list[str]) -> dict[str, list[str]]:
	"""Open ToDo assignees for these profiles, oldest assignment first."""
	grouped: dict[str, list[str]] = {}
	for row in _todo_rows(profiles):
		if row.get("status") != "Open":
			continue
		profile = row.get("reference_name")
		person = row.get("allocated_to")
		if not profile or not person:
			continue
		bucket = grouped.setdefault(profile, [])
		if person not in bucket:
			bucket.append(person)
	return grouped


def _todo_rows(profiles: list[str]) -> list[dict]:
	"""One ToDo read for every profile in the inbox page."""
	names = [name for name in profiles if name]
	if not names:
		return []
	try:
		if not frappe.db.exists("DocType", "ToDo"):
			return []
		rows = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "WA Profile",
				"reference_name": ["in", names],
			},
			fields=["reference_name", "allocated_to", "status", "priority"],
			order_by="creation asc",
			limit_page_length=0,
		)
	except Exception:
		return []
	if not isinstance(rows, list):
		return []
	clean = []
	for row in rows:
		if not isinstance(row, dict):
			continue
		clean.append(
			{
				"reference_name": row.get("reference_name"),
				"allocated_to": row.get("allocated_to"),
				"status": row.get("status"),
				"priority": row.get("priority"),
			}
		)
	return clean


def _assignees_for(name: str, fallback: str | None = None) -> list[str]:
	people = _open_assignees(name)
	if not people:
		raw = frappe.db.get_value("WA Profile", name, "_assign") if _has_column("_assign") else None
		people = _parse_assign(raw)
	if fallback and fallback not in people:
		people.append(fallback)
	return people


def _remove_assignment(name: str, user: str) -> None:
	"""Cancel one person's ToDo the way Frappe removes a document assignment."""
	from frappe.desk.form.assign_to import remove

	remove("WA Profile", name, user)


def _close_todos(name: str):
	if not name:
		return
	try:
		from frappe.desk.form.assign_to import close_all_assignments

		close_all_assignments("WA Profile", name, ignore_permissions=True)
		return
	except Exception:
		frappe.log_error(title="Nudg assign ToDo")
	todos = frappe.get_all(
		"ToDo",
		filters={"reference_type": "WA Profile", "reference_name": name, "status": "Open"},
		pluck="name",
	)
	if not isinstance(todos, list):
		return
	for todo in todos:
		frappe.db.set_value("ToDo", todo, "status", "Closed")


def _iso(val) -> str | None:
	if not val:
		return None
	if hasattr(val, "isoformat"):
		return val.isoformat()
	return str(val)


def _serialize(
	doc,
	assignees: list[str] | None = None,
	*,
	status: str | None = None,
	source: str | None = None,
	last_assigned: Any = None,
	tags: list[str] | None = None,
) -> dict:
	if tags is None:
		tags = _tags_of(doc)
	tags_list = [str(tag).strip() for tag in tags if str(tag).strip()]
	if assignees is None:
		assignees = _resolved_assignees(doc)
	assignees = [person for person in assignees if person]
	if status is None:
		status = _status_for(doc, assignees)
	if status != "Assigned":
		assignees = []
	primary = assignees[0] if assignees else None
	profile = _profile_name(doc)
	if last_assigned is None and profile:
		last_assigned = _cache_hash(RR_PROFILE_HASH).get(profile)
	if source is None and profile:
		cached_source = _cache_hash(SOURCE_HASH).get(profile)
		if isinstance(cached_source, str) and cached_source:
			source = cached_source
	return {
		"name": getattr(doc, "name", None),
		"profile": profile,
		"assignee": primary,
		"assignees": list(assignees),
		"assignment_status": status,
		"conversation_status": None,
		"priority": "Medium",
		"last_assigned_on": _iso(last_assigned) if last_assigned else None,
		"assignment_source": source,
		"whatsapp_account": _text(doc, "whatsapp_account"),
		"tags": tags_list,
		"tags_str": ", ".join(tags_list),
	}


def _resolved_assignees(doc) -> list[str]:
	known = _raw_field(doc, "_assign")
	if isinstance(known, (str, list)):
		people = _parse_assign(known)
		if people:
			return people
	name = getattr(doc, "name", None)
	if name:
		people = _open_assignees(name)
		if people:
			return people
		if isinstance(known, (str, list)):
			return []
	return _doc_assignees(doc)


def apply_legacy_profile_state(
	profile: str,
	*,
	assignee: str | None = None,
	assignment_status: str | None = None,
	tags: Any = None,
	priority: str | None = None,
	last_assigned_on: Any = None,
	source: str | None = None,
) -> None:
	"""Copy one legacy assignment onto ToDo, ``_assign``, ``_user_tags``, and Redis."""
	if not profile:
		return
	status = assignment_status or ("Assigned" if assignee else "Unassigned")
	if assignee and status == "Assigned" and assignee not in _open_assignees(profile):
		doc = frappe.get_doc("WA Profile", profile)
		_sync_todo(doc, user=assignee, priority=priority)
	elif status == "Closed":
		if assignee and assignee not in _open_assignees(profile) and not _todo_rows([profile]):
			doc = frappe.get_doc("WA Profile", profile)
			_sync_todo(doc, user=assignee, priority=priority)
		_close_todos(profile)
	if tags not in (None, ""):
		_tags_str, tags_list = _normalize_tags(tags)
		if tags_list:
			from frappe.desk.doctype.tag.tag import add_tag

			for tag in tags_list:
				add_tag(tag, "WA Profile", profile)
	clean_source = source if source in _SOURCES else None
	stamp = _iso(last_assigned_on) if last_assigned_on else None
	if assignee and stamp:
		_cache_hset(RR_HASH, assignee, stamp)
	if stamp:
		_cache_hset(RR_PROFILE_HASH, profile, stamp)
	if clean_source:
		_cache_hset(SOURCE_HASH, profile, clean_source)


def migrate_legacy_profile_fields() -> None:
	"""Move leftover custom assignment columns onto standard Frappe structures."""
	if not getattr(getattr(frappe, "local", None), "db", None):
		return
	try:
		if not frappe.db.table_exists("WA Profile"):
			return
	except Exception:
		return
	legacy = [
		name
		for name in ("assignee", "assignment_status", "tags", "priority", "last_assigned_on", "assignment_source")
		if _has_column(name)
	]
	if not any(name in legacy for name in ("assignee", "tags", "assignment_status")):
		return
	try:
		rows = frappe.get_all("WA Profile", fields=["name", *legacy], limit_page_length=0)
	except Exception:
		frappe.log_error(title="Nudg assignment migration")
		return
	if not isinstance(rows, list):
		return
	for row in rows:
		name = row.get("name") if isinstance(row, dict) else getattr(row, "name", None)
		if not name:
			continue
		try:
			apply_legacy_profile_state(
				name,
				assignee=row.get("assignee") if isinstance(row, dict) else None,
				assignment_status=row.get("assignment_status") if isinstance(row, dict) else None,
				tags=row.get("tags") if isinstance(row, dict) else None,
				priority=row.get("priority") if isinstance(row, dict) else None,
				last_assigned_on=row.get("last_assigned_on") if isinstance(row, dict) else None,
				source=row.get("assignment_source") if isinstance(row, dict) else None,
			)
		except Exception:
			frappe.log_error(title="Nudg assignment migration")
