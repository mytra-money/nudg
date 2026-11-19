# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Manual and rule-driven assignment, tags, notes, and auto-routing on WA Profile."""

from __future__ import annotations

import datetime
import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime


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


def ensure_conversation(profile: str, whatsapp_account: str | None = None, organization: str | None = None) -> str:
	"""Return the WA Profile for this chat. Assignment is stored on the profile."""
	if not profile or not frappe.db.exists("WA Profile", profile):
		frappe.throw(_("Profile {0} does not exist.").format(profile), frappe.DoesNotExistError)

	updates: dict[str, str] = {}
	if whatsapp_account and not frappe.db.get_value("WA Profile", profile, "whatsapp_account"):
		updates["whatsapp_account"] = whatsapp_account
	if _has_column("assignment_status") and not frappe.db.get_value("WA Profile", profile, "assignment_status"):
		updates["assignment_status"] = "Unassigned"
	if _has_column("priority") and not frappe.db.get_value("WA Profile", profile, "priority"):
		updates["priority"] = "Medium"
	if updates:
		frappe.db.set_value("WA Profile", profile, updates, update_modified=False)
	return profile


def _has_column(fieldname: str) -> bool:
	try:
		return bool(frappe.db.has_column("WA Profile", fieldname))
	except Exception:
		return False


def _profile_name(doc) -> str | None:
	return getattr(doc, "profile", None) or getattr(doc, "name", None)


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
	the other ToDos.
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

	_sync_todo(doc, user=canonical)
	doc.assignee = canonical
	doc.assignment_status = "Assigned"
	doc.assignment_source = source if source in ("Manual", "Assignment Rule", "Round Robin") else "Manual"
	doc.last_assigned_on = _safe_now()
	doc.save()

	_notify_inbox(name)
	return _serialize(doc, _assignees_for(name, fallback=canonical))


def unassign_conversation(profile: str, user: str | None = None) -> dict:
	"""Remove one assignee, or everyone when ``user`` is empty.

	Removing one person cancels only that person's ToDo, the same way Frappe
	removes a single assignment.
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
		if doc.assignee and doc.assignee != canonical and doc.assignee not in remaining:
			remaining.append(doc.assignee)
		if not remaining or doc.assignee == canonical or doc.assignee not in remaining:
			doc.assignee = remaining[-1] if remaining else None
		doc.assignment_status = "Assigned" if remaining else "Unassigned"
	else:
		doc.assignee = None
		doc.assignment_status = "Unassigned"
		doc.assignment_source = "Manual"
		_close_todos(name)
		remaining = []
	doc.save()
	_notify_inbox(name)
	return _serialize(doc, remaining)


def close_conversation(profile: str) -> dict:
	name = ensure_conversation(profile)
	doc = frappe.get_doc("WA Profile", name)
	frappe.has_permission("WA Profile", "write", doc=doc, throw=True)
	doc.assignment_status = "Closed"
	doc.save()
	_close_todos(doc.name)
	_notify_inbox(name)
	return _serialize(doc)


def _notify_inbox(profile: str | None) -> None:
	"""Ask the desk API to push this conversation. Never fails the assignment write."""
	if not profile:
		return
	try:
		from nudg.api import publish_inbox_change

		publish_inbox_change(profile, bump=False)
	except Exception:
		pass


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


def set_conversation_tags(profile: str, tags: Any) -> dict:
	"""Set multi-tags on conversation and propagate to contact model."""
	if not profile:
		frappe.throw(_("Profile is required."))

	tags_str, tags_list = _normalize_tags(tags)
	name = ensure_conversation(profile)
	doc = frappe.get_doc("WA Profile", name)
	frappe.has_permission("WA Profile", "write", doc=doc, throw=True)

	doc.tags = tags_str
	doc.save(ignore_permissions=True)
	_notify_inbox(_profile_name(doc))

	# Broadcast realtime update
	frappe.publish_realtime(
		"nudg_conversation_tags_updated",
		{
			"profile": _profile_name(doc),
			"conversation": _profile_name(doc),
			"tags": tags_list,
			"tags_str": tags_str,
			"user": getattr(getattr(frappe, "session", None), "user", None),
		},
		after_commit=False,
	)

	return _serialize(doc)


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

	# If already assigned, return current state without reassigning
	if getattr(doc, "assignee", None) and getattr(doc, "assignment_status", None) == "Assigned":
		return _serialize(doc)

	agents = get_eligible_desk_agents()
	if not agents:
		return _serialize(doc)

	# 1. Inspect recent assignments for active agents
	latest_assignments: dict[str, Any] = {a: None for a in agents}
	recent_rows = frappe.get_all(
		"WA Profile",
		filters={"assignee": ["in", agents], "assignment_status": "Assigned"},
		fields=["assignee", "last_assigned_on"],
		order_by="last_assigned_on desc",
		limit_page_length=500,
	)
	for r in recent_rows:
		assignee_val = r.get("assignee") if isinstance(r, dict) else getattr(r, "assignee", None)
		assigned_on_val = r.get("last_assigned_on") if isinstance(r, dict) else getattr(r, "last_assigned_on", None)
		if assignee_val in latest_assignments and latest_assignments[assignee_val] is None:
			latest_assignments[assignee_val] = assigned_on_val

	# 2. Select agent: prioritize never-assigned candidates, then oldest last_assigned_on
	never_assigned = [a for a in agents if latest_assignments[a] is None]
	if never_assigned:
		cache_key = "nudg_rr_unassigned_ptr"
		try:
			ptr = frappe.cache().get_value(cache_key) or 0
			idx = int(ptr) % len(never_assigned)
			selected_agent = never_assigned[idx]
			frappe.cache().set_value(cache_key, idx + 1)
		except Exception:
			selected_agent = never_assigned[0]
	else:
		selected_agent = min(
			agents,
			key=lambda a: (_safe_parse_datetime(latest_assignments[a]), a),
		)

	# 3. Apply assignment
	doc.assignee = selected_agent
	doc.assignment_status = "Assigned"
	doc.assignment_source = "Round Robin"
	doc.last_assigned_on = _safe_now()
	if hasattr(doc, "save"):
		doc.save(ignore_permissions=True)

	_sync_todo(doc)
	_notify_inbox(_profile_name(doc))

	frappe.publish_realtime(
		"nudg_conversation_assigned",
		{
			"profile": _profile_name(doc),
			"conversation": _profile_name(doc),
			"assignee": selected_agent,
			"assignment_source": "Round Robin",
		},
		after_commit=False,
	)

	return _serialize(doc)


# -----------------------------------------------------------------------------
# Helpers & Normalization
# -----------------------------------------------------------------------------

def get_conversation_map(profiles: list[str]) -> dict[str, dict]:
	if not profiles or not _has_column("assignment_status"):
		return {}
	rows = frappe.get_all(
		"WA Profile",
		filters={"name": ["in", profiles]},
		fields=[
			"name",
			"assignee",
			"assignment_status",
			"conversation_status",
			"priority",
			"last_assigned_on",
			"assignment_source",
			"whatsapp_account",
			"tags",
		],
	)
	todo_map = _assignees_by_profile(profiles)
	mapped: dict[str, dict] = {}
	for row in rows or []:
		name = row.get("name") if isinstance(row, dict) else getattr(row, "name", None)
		if not name:
			continue
		data = dict(row)
		data["profile"] = name
		people = list(todo_map.get(name) or [])
		single = data.get("assignee")
		if single and single not in people and data.get("assignment_status") != "Unassigned":
			people.append(single)
		data["assignees"] = people
		mapped[name] = data
	return mapped


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
	"""Save an internal note on the conversation. The note is not delivered to WhatsApp."""
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
	comment = frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": "WA Profile",
			"reference_name": name,
			"content": text,
			"comment_email": frappe.session.user,
			"comment_by": author,
		}
	)
	comment.insert(ignore_permissions=True)
	return {"status": "success", "notes": list_conversation_notes(profile)}


def on_conversation_update(doc, method=None):
	"""After Assignment Rule or form save, normalize stored assignment fields."""
	if not _has_column("assignment_status"):
		return
	if doc.assignee and doc.assignment_status == "Unassigned":
		doc.db_set("assignment_status", "Assigned", update_modified=False)
	if not doc.assignee and doc.assignment_status == "Assigned" and not _open_assignees(doc.name):
		doc.db_set("assignment_status", "Unassigned", update_modified=False)
	if doc.assignee and not doc.assignment_source:
		doc.db_set("assignment_source", "Assignment Rule", update_modified=False)
	if doc.assignee and not doc.last_assigned_on:
		doc.db_set("last_assigned_on", _safe_now(), update_modified=False)
	previous = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
	previous_assignee = getattr(previous, "assignee", None) if previous else None
	if (
		doc.assignee
		and doc.assignee != previous_assignee
		and not getattr(getattr(doc, "flags", None), "nudg_syncing_todo", False)
	):
		_sync_todo(doc)


def _sync_todo(doc, user: str | None = None):
	"""Create the Frappe assignment ToDo for this user without removing anyone else."""
	assignee = user or getattr(doc, "assignee", None)
	name = getattr(doc, "name", None)
	if not assignee or not name or _has_open_todo(name, assignee):
		return
	try:
		from frappe.desk.form.assign_to import add as add_assignment

		if getattr(doc, "flags", None) is not None:
			doc.flags.nudg_syncing_todo = True
		add_assignment(
			{
				"assign_to": [assignee],
				"doctype": "WA Profile",
				"name": name,
				"description": _("WhatsApp conversation {0}").format(_profile_name(doc) or name),
				"priority": getattr(doc, "priority", None) or "Medium",
			}
		)
	except Exception:
		if getattr(doc, "flags", None) is not None:
			doc.flags.nudg_syncing_todo = False
		frappe.log_error(title="Nudg assign ToDo")


def _has_open_todo(name: str, user: str) -> bool:
	return user in _open_assignees(name)


def _open_assignees(name: str) -> list[str]:
	grouped = _assignees_by_profile([name])
	return list(grouped.get(name) or [])


def _assignees_by_profile(profiles: list[str]) -> dict[str, list[str]]:
	"""Open ToDo assignees for these profiles, oldest assignment first."""
	if not profiles:
		return {}
	try:
		if not frappe.db.exists("DocType", "ToDo"):
			return {}
		rows = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "WA Profile",
				"reference_name": ["in", profiles],
				"status": "Open",
			},
			fields=["reference_name", "allocated_to"],
			order_by="creation asc",
			limit_page_length=0,
		)
	except Exception:
		return {}
	if not isinstance(rows, list):
		return {}
	grouped: dict[str, list[str]] = {}
	for row in rows:
		profile = row.get("reference_name") if isinstance(row, dict) else getattr(row, "reference_name", None)
		person = row.get("allocated_to") if isinstance(row, dict) else getattr(row, "allocated_to", None)
		if not profile or not person:
			continue
		bucket = grouped.setdefault(profile, [])
		if person not in bucket:
			bucket.append(person)
	return grouped


def _assignees_for(name: str, fallback: str | None = None) -> list[str]:
	people = _open_assignees(name)
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
		frappe.db.set_value("ToDo", todo, "status", "Cancelled")


def _iso(val) -> str | None:
	if not val:
		return None
	if hasattr(val, "isoformat"):
		return val.isoformat()
	return str(val)


def _serialize(doc, assignees: list[str] | None = None) -> dict:
	tags_str = getattr(doc, "tags", "") or ""
	tags_list = [t.strip() for t in str(tags_str).split(",") if t.strip()]
	last_assigned = getattr(doc, "last_assigned_on", None)
	if assignees is None:
		single = getattr(doc, "assignee", None)
		assignees = [single] if single else []
	primary = assignees[-1] if assignees else getattr(doc, "assignee", None)
	return {
		"name": getattr(doc, "name", None),
		"profile": _profile_name(doc),
		"assignee": primary,
		"assignees": list(assignees),
		"assignment_status": getattr(doc, "assignment_status", None),
		"conversation_status": getattr(doc, "conversation_status", None),
		"priority": getattr(doc, "priority", None),
		"last_assigned_on": _iso(last_assigned) if last_assigned else None,
		"assignment_source": getattr(doc, "assignment_source", None),
		"whatsapp_account": getattr(doc, "whatsapp_account", None),
		"tags": tags_list,
		"tags_str": tags_str,
	}
