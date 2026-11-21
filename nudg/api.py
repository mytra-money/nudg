"""Inbox API for the official WhatsApp app.

Every method refuses Guest. Inbox reads go through ``frappe.get_list``, so a
user only sees WhatsApp profiles and messages their roles already allow.
Official WhatsApp calls go through ``nudg.integrations.whatsapp``
and are imported there inside functions, so this module loads when that app
is absent. Account tokens are never selected.
"""

from __future__ import annotations

import json
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from nudg.integrations.whatsapp import adapter
from nudg.paging import page_limit, page_start
from nudg.services import assignments, chatbot
from nudg.utils.conversation_status import conversation_status
from nudg.utils.errors import format_error_message
from nudg.utils.phone import normalize_mobile_no, phone_match_key


def _safe_now():
	try:
		return now_datetime()
	except Exception:
		import datetime
		return datetime.datetime.now()


MESSAGE_FIELDS = [
	"name",
	"direction",
	"to",
	"from",
	"mime_type",
	"is_template",
	"media_url",
	"whatsapp_template",
	"message_id",
	"context_message_id",
	"reply_to_message",
	"creation",
	"message",
	"status",
	"reference_doctype",
	"reference_docname",
	"reaction",
	"error_code",
	"error_message",
	"whatsapp_account",
]

PROFILE_FIELDS = ["name", "profile_name", "phone_number", "whatsapp_account", "status", "wa_id"]


def _profile_column(fieldname: str) -> bool:
	try:
		return bool(frappe.db.has_column("WA Profile", fieldname))
	except Exception:
		return False


def _profile_fields() -> list[str]:
	fields = list(PROFILE_FIELDS)
	for optional in ("_user_tags", "_assign"):
		if _profile_column(optional):
			fields.append(optional)
	return fields


def _tag_parts(raw) -> list[str]:
	if isinstance(raw, (list, tuple)):
		return [str(part).strip() for part in raw if str(part).strip()]
	return [part.strip() for part in str(raw or "").split(",") if part.strip()]
ACCOUNT_FIELDS = ["name", "account_name", "status", "phone_id", "business_id", "app_id", "auto_read_receipts"]
TEMPLATE_FIELDS = [
	"name",
	"template_label",
	"template_name",
	"template_type",
	"language",
	"status",
	"header_text",
	"header_type",
	"header_media",
	"mime_type",
	"message",
	"footer",
	"reference_doctype",
	"whatsapp_account",
	"variable_format",
]
WINDOW = timedelta(hours=24)
INBOX_PAGE = 30
THREAD_PAGE = 40
LOG_PAGE = 40
TEMPLATE_PAGE = 50


def has_app_permission() -> bool:
	if frappe.session.user == "Guest":
		return False
	if not frappe.db.exists("DocType", "WA Message"):
		return True
	try:
		return bool(frappe.has_permission("WA Message", "read"))
	except Exception:
		return True


@frappe.whitelist()
def get_integration_status() -> dict:
	"""Installation status for the Overview page. Takes no filters.

	Guests and users who fail ``has_app_permission`` get ``PermissionError``.
	The dict is built by the adapter and contains no tokens or message bodies.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to open Nudg."), frappe.PermissionError)
	if not has_app_permission():
		frappe.throw(_("Not permitted to read WhatsApp messages."), frappe.PermissionError)
	return adapter.get_integration_status()


def _empty_inbox() -> dict:
	return {
		"mode": "live",
		"connected": False,
		"user": frappe.session.user,
		"site": frappe.local.site,
		"default_account": None,
		"can_read_logs": True,
		"accounts": [],
		"templates": [],
		"conversations": [],
		"queue_counts": {"all": 0, "mine": 0, "unassigned": 0, "bot": 0, "transferred": 0},
		"has_more": False,
		"start": 0,
	}


def _assignment_people(assignment: dict | None) -> tuple[str | None, list[str]]:
	"""Primary assignee plus every open assignee. Unassigned conversations have neither."""
	assignment = assignment or {}
	status = assignment.get("assignment_status") or "Unassigned"
	raw = assignment.get("assignees")
	people: list[str] = []
	if isinstance(raw, list):
		for person in raw:
			if person and person not in people:
				people.append(person)
	single = assignment.get("assignee")
	if single and single not in people and status == "Assigned":
		people.append(single)
	if status != "Assigned":
		people = []
	primary = people[0] if people else None
	return primary, people


def _conversation_item(profile, preview, last_incoming, assignment, unread_count: int = 0, bot_info: dict | None = None) -> dict:
	"""One inbox card. Shared by the list endpoint and the socket payload."""
	window = _window(last_incoming)
	status = conversation_status(profile, preview, window)
	raw_tags = assignment.get("tags") or ""
	conv_tags = _tag_parts(raw_tags)
	phone_norm = normalize_mobile_no(profile.phone_number)
	if bot_info is None:
		bot_info = chatbot.get_bot_status(profile.phone_number, profile.whatsapp_account)
	assignee, assignees = _assignment_people(assignment)
	return {
		"profile": profile,
		"phone_normalized": phone_norm,
		"bot_status": bot_info,
		"preview": preview,
		"window": window,
		"conversation_status": status,
		"needs_reply": status == "needs_reply",
		"failed": status == "failed",
		"tags": conv_tags,
		"tags_str": str(raw_tags),
		"unread_count": int(unread_count or 0),
		"assignment": {
			"name": assignment.get("name"),
			"assignee": assignee,
			"assignees": assignees,
			"assignment_status": assignment.get("assignment_status") or "Unassigned",
			"priority": assignment.get("priority"),
			"assignment_source": assignment.get("assignment_source"),
			"last_assigned_on": _iso(assignment.get("last_assigned_on"))
			if assignment.get("last_assigned_on")
			else None,
			"tags": conv_tags,
		},
	}


@frappe.whitelist()
def get_inbox(
	account: str | None = None,
	tag: str | None = None,
	tags: str | None = None,
	queue: str | None = "all",
	start: int | None = 0,
	limit: int | None = None,
) -> dict:
	if not _ready():
		return _empty_inbox()
	if account:
		_assert_account_allowed(account)
	page_size = page_limit(limit, default=INBOX_PAGE, maximum=INBOX_PAGE)
	offset = page_start(start)
	filter_tag = (tag or tags or "").strip().lower()
	queue_filter = (queue or "all").strip().lower()
	filtering = bool(filter_tag) or queue_filter not in ("", "all")
	# Filtered views scan a bounded window, then page the matches. The default
	# inbox reads one page of the most recently updated conversations.
	profile_filters = {"whatsapp_account": account} if account else {}
	if filtering:
		profiles = frappe.get_list(
			"WA Profile",
			fields=_profile_fields(),
			filters=profile_filters,
			order_by="modified desc",
			limit_page_length=120,
		)
	else:
		profiles = frappe.get_list(
			"WA Profile",
			fields=_profile_fields(),
			filters=profile_filters,
			order_by="modified desc",
			limit_start=offset,
			limit_page_length=page_size + 1,
		)
	has_more = False
	if not filtering:
		has_more = len(profiles) > page_size
		profiles = profiles[:page_size]
	profile_names = [row.name for row in profiles]
	latest, last_incoming = _latest_previews(profile_names)

	default_account = _default_account()
	assignment_map = assignments.get_conversation_map(profile_names) if profile_names else {}
	unread_counts = _unread_counts(profile_names)
	bot_map = chatbot.bot_status_for_profiles(profiles)

	conversations = []
	queue_counts = {"all": 0, "mine": 0, "unassigned": 0, "bot": 0, "transferred": 0}

	for profile in profiles:
		preview = latest.get(profile.name)
		assignment = assignment_map.get(profile.name) or {}
		conv_item = _conversation_item(
			profile,
			preview,
			last_incoming.get(profile.name),
			assignment,
			unread_counts.get(profile.name, 0),
			bot_map.get(profile.name),
		)

		raw_tags = assignment.get("tags") or ""
		conv_tags = conv_item["tags"]

		# Tag filter check
		if filter_tag:
			filter_items = [t.strip() for t in filter_tag.split(",") if t.strip()]
			conv_tags_lower = [t.lower() for t in conv_tags]
			match = any(
				fi in conv_tags_lower or fi in str(raw_tags).lower()
				for fi in filter_items
			)
			if not match:
				continue

		bot_info = conv_item["bot_status"]
		assignees = conv_item["assignment"]["assignees"]

		queue_counts["all"] += 1
		if frappe.session.user in assignees:
			queue_counts["mine"] += 1
		if not assignees:
			queue_counts["unassigned"] += 1
		if bot_info.get("has_bot_session"):
			queue_counts["bot"] += 1
		if bot_info.get("is_transferred"):
			queue_counts["transferred"] += 1

		# Queue Filter
		if queue_filter == "mine" and frappe.session.user not in assignees:
			continue
		if queue_filter == "unassigned" and assignees:
			continue
		if queue_filter == "bot" and not bot_info.get("has_bot_session"):
			continue
		if queue_filter == "transferred" and not bot_info.get("is_transferred"):
			continue

		conversations.append(conv_item)

	conversations.sort(key=_latest_activity, reverse=True)
	if filtering:
		has_more = len(conversations) > offset + page_size
		conversations = conversations[offset : offset + page_size]

	return {
		"mode": "live",
		"connected": True,
		"user": frappe.session.user,
		"site": frappe.local.site,
		"default_account": default_account,
		"can_read_logs": bool(frappe.has_permission("WA Log", "read")),
		"accounts": _accounts(default_account),
		"templates": [],
		"conversations": conversations,
		"queue_counts": queue_counts,
		"has_more": has_more,
		"start": offset,
	}


def _get_conversation_notes(profile: str) -> list[dict]:
	"""Internal notes stored as Comments on the conversation, separate from WA Messages."""
	from nudg.services.assignments import list_conversation_notes

	return list_conversation_notes(profile)


@frappe.whitelist()
def publish_presence(conversation_id: str, action: str) -> dict:
	"""Broadcast live agent presence (viewing, typing) over Socket.IO via frappe.publish_realtime."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to open Nudg."), frappe.PermissionError)

	if not conversation_id or not str(conversation_id).strip() or not action or not str(action).strip():
		frappe.throw(_("conversation_id and action are required."), frappe.ValidationError)

	conversation_id = str(conversation_id).strip()
	action = str(action).strip()

	if not frappe.db.exists("WA Profile", conversation_id):
		raise frappe.DoesNotExistError(_(f"Conversation {conversation_id} not found"))

	if not has_app_permission():
		raise frappe.PermissionError(_("Not permitted"))

	roles = frappe.get_roles() if hasattr(frappe, "get_roles") else []
	if not ("WhatsApp User" in roles or "System Manager" in roles or frappe.session.user == "Administrator"):
		try:
			if not frappe.has_permission("WA Profile", "read"):
				raise frappe.PermissionError(_("Not permitted"))
		except frappe.PermissionError:
			raise
		except Exception:
			pass

	act = action.lower()
	is_typing = "type" in act or "typing" in act
	is_active = "stop" not in act and "blur" not in act and "leave" not in act

	if is_typing:
		event_name = "nudg_agent_typing"
	else:
		event_name = "nudg_agent_viewing"

	user = frappe.session.user
	user_name = user
	try:
		user_name = frappe.utils.get_fullname(user) or user
	except Exception:
		pass

	payload = {
		"conversation_id": conversation_id,
		"user": user,
		"user_fullname": user_name,
		"action": action,
		"active": is_active,
		"timestamp": _safe_now().isoformat(),
	}

	frappe.publish_realtime(
		event=event_name,
		message=payload,
		after_commit=False,
	)

	return {
		"status": "published",
		"event": event_name,
		"conversation_id": conversation_id,
		"user": user,
		"payload": payload,
	}


@frappe.whitelist()
def get_thread(profile: str, before_creation: str | None = None, limit: int | None = None) -> dict:
	if not _ready():
		frappe.throw(_("WhatsApp is not connected on this site."))
	visible = frappe.get_list(
		"WA Profile",
		filters={"name": profile},
		fields=_profile_fields(),
		limit_page_length=1,
	)
	if not visible:
		frappe.throw(_("You can't open this conversation."), frappe.PermissionError)

	page_size = page_limit(limit, default=THREAD_PAGE, maximum=50)
	cursor = (before_creation or "").strip()
	from nudg.integrations.site_store import thread_messages

	remote = thread_messages(profile, cursor or None, page_size + 1)
	if remote is not None:
		raw = remote
	else:
		filters: dict = {"to": profile}
		if cursor:
			filters["creation"] = ["<", cursor]
		raw = frappe.get_list(
			"WA Message",
			filters=filters,
			fields=MESSAGE_FIELDS,
			order_by="creation desc",
			limit_page_length=page_size + 1,
		)
	has_older = len(raw) > page_size
	raw = list(reversed(raw[:page_size]))
	raw = [_stamp(row) for row in raw]
	rendered = _rendered_for(raw)
	by_name = {row.name: row for row in raw}
	for message in rendered:
		if message.get("to") != profile or not message.get("name"):
			continue
		current = by_name.setdefault(message["name"], {})
		for key, value in message.items():
			if key == "reaction" or value is None:
				continue
			current[key] = value
	folded = _fold(list(by_name.values()))
	_attach_templates(folded)

	notes = _get_conversation_notes(profile)
	prof = visible[0]
	raw_tags = prof.get("_user_tags") or ""
	if not raw_tags and _profile_column("_user_tags"):
		raw_tags = frappe.db.get_value("WA Profile", profile, "_user_tags") or ""
	tags_list = _tag_parts(raw_tags)

	# Marking messages read writes rows and may call Meta. Do that after the
	# response is committed so opening a thread stays a read.
	if not cursor:
		_enqueue_read_receipts(profile)

	bot_info = chatbot.get_bot_status(prof.get("phone_number"), prof.get("whatsapp_account"))

	return {
		"profile": prof,
		"messages": folded,
		"notes": notes,
		"tags": tags_list,
		"bot_status": bot_info,
		"window": _thread_window(profile, folded),
		"references": _references(folded),
		"links": _profile_links(profile),
		"has_older": has_older,
	}


def _enqueue_read_receipts(profile: str) -> None:
	if getattr(getattr(frappe.local, "flags", None), "in_test", False):
		return
	# The badge is the Read status. Apply it in this request so it does not wait
	# for a background worker. Telling Meta stays on the queue.
	message_ids: list[str] = []
	account_name = frappe.db.get_value("WA Profile", profile, "whatsapp_account")
	auto_read = bool(account_name and frappe.db.get_value("WA Account", account_name, "auto_read_receipts"))
	try:
		from nudg.integrations.site_store import mark_thread_read

		remote_ids = mark_thread_read(profile)
		if remote_ids is not None:
			message_ids = remote_ids
			publish_inbox_change(profile)
		elif _unread_counts([profile]).get(profile, 0):
			unread = frappe.get_all(
				"WA Message",
				filters={"to": profile, "direction": "Incoming", "status": ["not in", ["Read", "Failed"]]},
				fields=["message_id"],
				limit_page_length=50,
			)
			message_ids = [row.message_id for row in unread if row.get("message_id")]
			reaction_clause = ""
			if frappe.db.has_column("WA Message", "reaction"):
				reaction_clause = "and ifnull(`reaction`, '') = ''"
			frappe.db.sql(
				f"""
				update `tabWA Message`
				set status = 'Read'
				where `to` = %(profile)s
				  and direction = 'Incoming'
				  and ifnull(status, '') not in ('Read', 'Failed')
				  {reaction_clause}
				""",
				{"profile": profile},
			)
			publish_inbox_change(profile)
	except Exception:
		frappe.log_error(title="Nudg read receipt", message=frappe.get_traceback())
		return
	if not auto_read or not account_name or not message_ids:
		return
	try:
		frappe.enqueue(
			"nudg.api._send_auto_read_receipts",
			queue="short",
			timeout=120,
			enqueue_after_commit=True,
			profile=profile,
			account_name=account_name,
			message_ids=message_ids,
		)
	except Exception:
		pass


def _send_auto_read_receipts(profile: str, account_name: str | None = None, message_ids: list | None = None) -> None:
	"""Tell Meta that messages already marked Read were opened. The badge is set before this runs."""
	if not account_name or not message_ids:
		return
	try:
		for message_id in message_ids:
			try:
				adapter.mark_as_read(message_id, account_name)
			except Exception:
				frappe.log_error(title="WhatsApp read receipt", message=frappe.get_traceback())
		frappe.publish_realtime(
			"whatsapp_inbox_update",
			{"type": "read", "profile": profile},
		)
	except Exception as exc:
		frappe.log_error(title="Auto read receipt error", message=str(exc))


@frappe.whitelist()
def assign_agent(profile: str, agent: str | None = None) -> dict:
	"""Assign a conversation to an agent, with real-time Socket.IO notification."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to open Nudg."), frappe.PermissionError)
	if not profile:
		frappe.throw(_("Profile is required."))
	_assert_profile_allowed(profile)

	agent = (agent or "").strip()
	res = (
		assignments.assign_conversation(profile, agent, source="Manual", enforce_visibility=True)
		if agent
		else assignments.unassign_conversation(profile)
	)

	# If chatbot is installed, sync transfer / resume
	if chatbot.is_chatbot_installed():
		phone = frappe.db.get_value("WA Profile", profile, "phone_number")
		account = frappe.db.get_value("WA Profile", profile, "whatsapp_account")
		if agent and phone:
			try:
				chatbot.transfer_to_agent(phone, account=account, agent=agent, notes=_("Assigned from Nudg"))
			except Exception:
				pass
		elif not agent and phone:
			try:
				chatbot.resume_chatbot(phone, account=account)
			except Exception:
				pass

	frappe.publish_realtime(
		"whatsapp_inbox_update",
		{
			"type": "assignment",
			"profile": profile,
			"assignee": agent,
			"assignment_status": "Assigned" if agent else "Unassigned",
		},
	)
	return res


@frappe.whitelist()
def get_assignable_agents(account: str | None = None) -> list[dict]:
	"""Return list of active agents permitted for the account."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to open Nudg."), frappe.PermissionError)

	from nudg.security import get_user_wa_accounts
	permitted = set(get_user_wa_accounts())
	if account and account not in permitted and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Permission denied."), frappe.PermissionError)

	names = assignments.get_assignable_account_users()
	if not assignments.can_view_team_users():
		me = frappe.session.user
		names = [me] if me in names else []
	if not names:
		return []
	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "name": ["in", names]},
		fields=["name", "full_name", "user_image"],
		order_by="full_name asc",
	)
	return [{"value": u.name, "label": u.full_name or u.name, "user_image": u.user_image} for u in users]


@frappe.whitelist()
def transfer_conversation_to_agent(profile: str, agent: str | None = None, notes: str | None = None) -> dict:
	"""Hand off a chatbot session to a human agent."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to open Nudg."), frappe.PermissionError)
	_assert_profile_allowed(profile)
	phone = frappe.db.get_value("WA Profile", profile, "phone_number")
	account = frappe.db.get_value("WA Profile", profile, "whatsapp_account")
	if not phone:
		frappe.throw(_("Profile phone number not found."))

	agent = agent or frappe.session.user
	res = chatbot.transfer_to_agent(phone, account=account, agent=agent, notes=notes)
	assignments.assign_conversation(profile, agent, source="Chatbot Transfer")
	return res


@frappe.whitelist()
def resume_conversation_chatbot(profile: str) -> dict:
	"""Resume automated chatbot for a conversation."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to open Nudg."), frappe.PermissionError)
	_assert_profile_allowed(profile)
	phone = frappe.db.get_value("WA Profile", profile, "phone_number")
	account = frappe.db.get_value("WA Profile", profile, "whatsapp_account")
	if not phone:
		frappe.throw(_("Profile phone number not found."))
	return chatbot.resume_chatbot(phone, account=account)


def _profiles_assigned_to(user: str) -> list[str]:
	"""Profiles with an open ToDo for this user."""
	names: list[str] = []
	try:
		todo_names = frappe.get_all(
			"ToDo",
			filters={"reference_type": "WA Profile", "allocated_to": user, "status": "Open"},
			pluck="reference_name",
			limit_page_length=0,
		)
		if isinstance(todo_names, list):
			names.extend(todo_names)
	except Exception:
		pass
	unique: list[str] = []
	for name in names:
		if name and name not in unique:
			unique.append(name)
	return unique


def _unassigned_profile_count() -> int | None:
	"""Profiles with nobody assigned and no Closed ToDo. None when ToDo cannot be read."""
	try:
		if not frappe.db.exists("DocType", "ToDo") or not frappe.db.exists("DocType", "WA Profile"):
			return None
		rows = frappe.get_all(
			"ToDo",
			filters={"reference_type": "WA Profile", "status": ["in", ["Open", "Closed"]]},
			fields=["reference_name", "status"],
			limit_page_length=0,
		)
		if not isinstance(rows, list):
			return None
		open_names: set[str] = set()
		closed_names: set[str] = set()
		for row in rows:
			name = row.get("reference_name") if isinstance(row, dict) else getattr(row, "reference_name", None)
			status = row.get("status") if isinstance(row, dict) else getattr(row, "status", None)
			if not name:
				continue
			if status == "Open":
				open_names.add(name)
			elif status == "Closed":
				closed_names.add(name)
		total = frappe.db.count("WA Profile")
		if not isinstance(total, int):
			return None
		return max(total - len(open_names) - len(closed_names - open_names), 0)
	except Exception:
		return None


@frappe.whitelist()
def get_unread_count() -> dict[str, int]:
	"""Return counts of unread, needs_reply, and open conversations for Desk navigation."""
	if not frappe.session or not frappe.session.user or frappe.session.user == "Guest":
		return {"unread": 0, "needs_reply": 0, "assigned_to_me": 0, "unassigned": 0}

	try:
		user = frappe.session.user
		needs_reply = 0
		assigned_to_me = 0
		unassigned = 0

		assigned_names = _profiles_assigned_to(user)
		assigned_to_me = len(assigned_names)

		native_unassigned = _unassigned_profile_count()
		if native_unassigned is not None:
			unassigned = native_unassigned

		unread_messages = 0
		if frappe.db.exists("DocType", "WA Message"):
			unread_messages = frappe.db.count(
				"WA Message",
				filters={"direction": "Incoming", "status": ["!=", "Read"]},
			)

		return {
			"unread": unread_messages,
			"needs_reply": needs_reply,
			"assigned_to_me": assigned_to_me,
			"unassigned": unassigned,
		}
	except Exception:
		return {"unread": 0, "needs_reply": 0, "assigned_to_me": 0, "unassigned": 0}


@frappe.whitelist()
def get_logs(account: str | None = None, start: int | None = 0, limit: int | None = None) -> list:
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to open Nudg."), frappe.PermissionError)
	if not frappe.db.exists("DocType", "WA Log"):
		return []
	if not frappe.has_permission("WA Log", "read"):
		frappe.throw(_("You can't read the WhatsApp log."), frappe.PermissionError)
	filters: dict = {}
	if account:
		_assert_account_allowed(account)
		filters["account"] = account
	else:
		allowed = _readable_accounts()
		if allowed is not None:
			filters["account"] = ["in", allowed or ["__none__"]]
	rows = frappe.get_list(
		"WA Log",
		fields=[
			"name",
			"level",
			"event_type",
			"timestamp",
			"account",
			"reference_doctype",
			"reference_docname",
			"message",
			"request_data",
			"response_data",
		],
		filters=filters,
		order_by="timestamp desc",
		limit_start=page_start(start),
		limit_page_length=page_limit(limit, default=LOG_PAGE, maximum=50),
	)
	for row in rows:
		row.timestamp = _iso(row.timestamp)
		row.request_data = _clip(row.request_data)
		row.response_data = _clip(row.response_data)
	return rows


def _readable_accounts() -> list[str] | None:
	"""Account names a non-admin may read. None leaves the list unscoped."""
	from nudg.security import _get_roles, get_user_wa_accounts

	user = getattr(frappe.session, "user", None)
	roles = _get_roles(user) if user else set()
	if user == "Administrator" or (isinstance(roles, (list, tuple, set)) and "System Manager" in roles):
		return None
	allowed = get_user_wa_accounts(user)
	if not isinstance(allowed, list):
		return None
	return [item for item in allowed if isinstance(item, str)]


def _assert_account_allowed(account: str | None) -> None:
	if not isinstance(account, str) or not account.strip():
		return
	allowed = _readable_accounts()
	if allowed is None:
		return
	if account not in allowed:
		frappe.throw(_("You do not have access to this WhatsApp account."), frappe.PermissionError)


def _assert_profile_allowed(profile: str) -> None:
	if not profile:
		return
	try:
		account = frappe.db.get_value("WA Profile", profile, "whatsapp_account")
	except Exception:
		return
	if isinstance(account, str):
		_assert_account_allowed(account)


def _row_dicts(value) -> list | None:
	if isinstance(value, list):
		return value
	return None


def _latest_previews(profile_names: list[str]) -> tuple[dict, dict]:
	"""One latest message and the last incoming time per conversation."""
	latest: dict[str, dict] = {}
	last_incoming: dict[str, str] = {}
	if not profile_names:
		return latest, last_incoming
	from nudg.integrations.site_store import previews, split_profiles

	local_names, remote_profiles = split_profiles(profile_names)
	remote_found, remote_local = previews(remote_profiles)
	local_names = list(local_names) + [name for name in remote_local if name not in local_names]
	for row in (_preview_rows(local_names) if local_names else []):
		stamped = _stamp(row)
		if stamped.get("reaction"):
			continue
		key = stamped.get("to")
		if not key or key in latest:
			continue
		latest[key] = stamped
		if stamped.get("direction") == "Incoming":
			last_incoming[key] = stamped.creation
	for row in (_last_incoming_rows(local_names) if local_names else []):
		key = row.get("profile") or row.get("to")
		created = row.get("creation")
		if key and created and key not in last_incoming:
			last_incoming[key] = _iso(created)
	for name, (preview, incoming) in remote_found.items():
		latest[name] = _stamp(preview)
		if incoming:
			last_incoming[name] = _iso(incoming)
	return latest, last_incoming


def _preview_rows(profile_names: list[str]) -> list:
	try:
		from frappe.query_builder import Order
		from frappe.query_builder.functions import IfNull, Max

		message = frappe.qb.DocType("WA Message")
		latest = (
			frappe.qb.from_(message)
			.select(message.to.as_("profile_name"), Max(message.creation).as_("latest_creation"))
			.where(message.to.isin(profile_names))
			.where(IfNull(message.reaction, "") == "")
			.groupby(message.to)
		).as_("latest")
		query = (
			frappe.qb.from_(message)
			.join(latest)
			.on((latest.profile_name == message.to) & (latest.latest_creation == message.creation))
			.select(*(getattr(message, field) for field in MESSAGE_FIELDS))
			.where(IfNull(message.reaction, "") == "")
			.orderby(message.creation, order=Order.desc)
		)
		rows = _row_dicts(query.run(as_dict=True))
		if rows is not None:
			return rows
	except Exception:
		pass
	cap = min(max(len(profile_names) * 3, INBOX_PAGE), 90)
	rows = frappe.get_list(
		"WA Message",
		fields=MESSAGE_FIELDS,
		filters={"to": ["in", profile_names]},
		order_by="creation desc",
		limit_page_length=cap,
	)
	return rows if isinstance(rows, list) else []


def _last_incoming_rows(profile_names: list[str]) -> list:
	try:
		from frappe.query_builder.functions import IfNull, Max

		message = frappe.qb.DocType("WA Message")
		query = (
			frappe.qb.from_(message)
			.select(message.to.as_("profile"), Max(message.creation).as_("creation"))
			.where(message.to.isin(profile_names))
			.where(message.direction == "Incoming")
			.where(IfNull(message.reaction, "") == "")
			.groupby(message.to)
		)
		rows = _row_dicts(query.run(as_dict=True))
		if rows is not None:
			return rows
	except Exception:
		pass
	return []


def _thread_window(profile: str, messages: list) -> dict:
	"""Window from the latest incoming message, including ones older than this page."""
	from nudg.integrations.site_store import last_incoming_at

	remote_at = last_incoming_at(profile)
	if remote_at is not None:
		return _window(remote_at or None)
	created = None
	try:
		created = frappe.db.get_value(
			"WA Message",
			{"to": profile, "direction": "Incoming"},
			"creation",
			order_by="creation desc",
		)
	except Exception:
		created = None
	if _looks_like_datetime(created):
		return _window(created)
	return _window_from_messages(messages)


def _looks_like_datetime(value) -> bool:
	from datetime import date, datetime

	if isinstance(value, (datetime, date)):
		return True
	if not isinstance(value, str):
		return False
	text = value.strip()
	return len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-"


def _ready() -> bool:
	"""True when this site's WhatsApp API can be read.

	The desk does not check the Frappe version. A logged-in user either gets
	the inbox from the site API, or an empty payload when that API is absent.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to open Nudg."), frappe.PermissionError)
	if not frappe.db.exists("DocType", "WA Message"):
		return False
	if not frappe.has_permission("WA Message", "read"):
		frappe.throw(_("Not permitted to read WhatsApp messages."), frappe.PermissionError)
	return True


def _default_account() -> str | None:
	if not frappe.db.exists("DocType", "WA Settings"):
		return None
	return frappe.db.get_single_value("WA Settings", "default_account")


def _accounts(default_account: str | None) -> list:
	if not frappe.db.exists("DocType", "WA Account"):
		return []
	from nudg.security import cache_get, cache_set, get_assigned_wa_accounts, get_user_wa_accounts
	user = getattr(frappe.session, "user", None)
	user_accounts = get_user_wa_accounts(user)
	if not isinstance(user_accounts, list) or not user_accounts:
		return []
	cache_key = f"nudg:accounts-meta:{user}:{','.join(user_accounts)}"
	cached = cache_get(cache_key)
	if isinstance(cached, list):
		rows = [dict(row) for row in cached]
	else:
		assigned = set(get_assigned_wa_accounts(user))
		rows = frappe.get_all(
			"WA Account",
			filters={"name": ["in", user_accounts]},
			fields=ACCOUNT_FIELDS,
			order_by="account_name asc",
			limit_page_length=50,
		)
		if not isinstance(rows, list):
			return []
		for row in rows:
			row["assigned"] = row.name in assigned
			row["auto_read_receipts"] = bool(row.auto_read_receipts)
		cache_set(cache_key, [dict(row) for row in rows], 120)
		rows = [dict(row) for row in rows]
	for row in rows:
		row["is_default"] = row.get("name") == default_account
	return rows


@frappe.whitelist()
def get_templates(account: str | None = None, start: int | None = 0, limit: int | None = None) -> list:
	"""Approved and draft templates for the composer. Not part of the inbox payload."""
	if not _ready():
		return []
	if account:
		_assert_account_allowed(account)
	offset = page_start(start)
	page_size = page_limit(limit, default=TEMPLATE_PAGE, maximum=100)
	user = getattr(frappe.session, "user", None) or "Guest"
	cache_key = f"nudg:templates:{user}:{account or 'all'}:{offset}:{page_size}"
	from nudg.security import cache_get, cache_set

	cached = cache_get(cache_key)
	if isinstance(cached, list):
		return cached
	rows = _templates(account, start=offset, limit=page_size)
	cache_set(cache_key, rows, 300)
	return rows


def _templates(account: str | None = None, start: int = 0, limit: int = TEMPLATE_PAGE) -> list:
	if not frappe.has_permission("WA Template", "read"):
		return []
	window = start + limit
	rows = frappe.get_list(
		"WA Template",
		fields=TEMPLATE_FIELDS,
		order_by="modified desc",
		limit_page_length=window,
	)
	if account:
		rows = [row for row in rows if not row.whatsapp_account or row.whatsapp_account == account]
	rows = rows[start:window]
	_attach_template_buttons(rows)
	_attach_template_variables(rows)
	return rows


def _attach_template_variables(rows: list) -> None:
	names = [row.name for row in rows]
	if not names or not frappe.db.exists("DocType", "WA Template Variable"):
		for row in rows:
			row["template_variables"] = []
		return
	variables = frappe.get_all(
		"WA Template Variable",
		filters={"parent": ["in", names], "parenttype": "WA Template"},
		fields=["parent", "variable_name", "variable_example", "variable_field", "idx"],
		order_by="idx asc",
		limit_page_length=max(len(names) * 20, 1),
	)
	grouped: dict[str, list] = {}
	for variable in variables:
		grouped.setdefault(variable.parent, []).append(
			{
				"variable_name": variable.variable_name,
				"variable_example": variable.variable_example,
				"variable_field": variable.variable_field,
			}
		)
	for row in rows:
		row["template_variables"] = grouped.get(row.name, [])


def _attach_template_buttons(rows: list) -> None:
	names = [row.name for row in rows]
	if not names or not frappe.db.exists("DocType", "WA Template Button"):
		for row in rows:
			row["buttons"] = []
		return
	buttons = frappe.get_all(
		"WA Template Button",
		filters={"parent": ["in", names], "parenttype": "WA Template"},
		fields=["parent", "button_type", "button_text", "url", "phone_number", "idx"],
		order_by="idx asc",
		limit_page_length=1000,
	)
	grouped: dict[str, list] = {}
	for button in buttons:
		grouped.setdefault(button.parent, []).append(
			{
				"button_type": button.button_type,
				"button_text": button.button_text,
				"url": button.url,
				"phone_number": button.phone_number,
			}
		)
	for row in rows:
		row["buttons"] = grouped.get(row.name, [])


def _rendered_for(raw: list) -> list:
	pairs = []
	seen = set()
	for row in raw:
		doctype = row.get("reference_doctype")
		docname = row.get("reference_docname")
		if not doctype or not docname:
			continue
		key = (doctype, docname)
		if key in seen:
			continue
		seen.add(key)
		if not frappe.db.exists("DocType", doctype) or not frappe.db.exists(doctype, docname):
			continue
		if frappe.has_permission(doctype, "read", docname):
			pairs.append([doctype, docname])
	if not pairs:
		return []
	return adapter.get_messages(json.dumps(pairs)) or []


def _fold(messages: list) -> list:
	ordered = sorted(messages, key=lambda row: (row.get("creation") or "", row.get("name") or ""))
	# A retried webhook can leave two WA Message rows for one WhatsApp id.
	# Keep the earliest so the thread shows that message once.
	seen_ids: set[str] = set()
	deduped = []
	for row in ordered:
		message_id = row.get("message_id")
		if message_id:
			if message_id in seen_ids:
				continue
			seen_ids.add(message_id)
		deduped.append(row)
	ordered = deduped
	by_id = {row.get("message_id"): row for row in ordered if row.get("message_id")}
	by_name = {row.get("name"): row for row in ordered}
	reactions: dict[str, dict[str, str]] = {}
	visible = []
	for row in ordered:
		target = row.get("context_message_id") or ""
		if not target and row.get("reaction") and row.get("reply_to_message"):
			quoted = by_name.get(row.get("reply_to_message"))
			target = (quoted or {}).get("message_id") or ""
		# NULL reaction is a normal message, including a reply. An empty string
		# with a target is a retraction of an earlier emoji.
		if row.get("reaction") is None or not target:
			visible.append(row)
			continue
		bucket = reactions.setdefault(target, {})
		direction = row.get("direction") or "Outgoing"
		if row.get("reaction"):
			bucket[direction] = row.get("reaction")
		else:
			bucket.pop(direction, None)

	for row in visible:
		row["reactions"] = [
			{"emoji": emoji, "direction": direction}
			for direction, emoji in reactions.get(row.get("message_id") or "", {}).items()
		]
		quoted = None
		if row.get("reply_to_message"):
			quoted = by_name.get(row.get("reply_to_message"))
		elif row.get("context_message_id"):
			quoted = by_id.get(row.get("context_message_id"))
		if quoted and not quoted.get("reaction"):
			row["reply_to"] = quoted.get("name")
			row["reply_to_direction"] = quoted.get("direction")
			row["reply_message"] = quoted.get("template") or quoted.get("message") or quoted.get("file_name") or _("Attachment")
		row["is_template"] = bool(row.get("is_template"))
	return visible


def _attach_templates(messages: list) -> None:
	pending = [
		row
		for row in messages
		if row.get("is_template") and row.get("whatsapp_template") and not row.get("template")
	]
	if not pending or not frappe.has_permission("WA Template", "read"):
		return
	names = list({row.get("whatsapp_template") for row in pending})
	templates = {
		row.name: row
		for row in frappe.get_list(
			"WA Template",
			filters={"name": ["in", names]},
			fields=["name", "template_label", "message", "header_text", "footer"],
			limit_page_length=len(names),
		)
	}
	_attach_template_buttons(list(templates.values()))
	for row in pending:
		template = templates.get(row.get("whatsapp_template"))
		if not template:
			continue
		row["template"] = template.message
		row["header"] = template.header_text
		row["footer"] = template.footer
		row["buttons"] = template.buttons
		row["template_label"] = template.template_label


def _references(messages: list) -> list:
	seen = set()
	refs = []
	for row in messages:
		doctype = row.get("reference_doctype")
		docname = row.get("reference_docname")
		if not doctype or not docname or (doctype, docname) in seen:
			continue
		seen.add((doctype, docname))
		if frappe.db.exists("DocType", doctype) and frappe.has_permission(doctype, "read", docname):
			refs.append({"doctype": doctype, "docname": docname})
		if len(refs) >= 20:
			break
	return refs


def _profile_links(profile: str) -> list:
	if not frappe.db.exists("DocType", "Dynamic Link"):
		return []
	rows = frappe.get_all(
		"Dynamic Link",
		filters={"parent": profile, "parenttype": "WA Profile"},
		fields=["link_doctype", "link_name", "link_title"],
		limit_page_length=30,
	)
	visible = []
	for row in rows:
		if not row.link_doctype or not row.link_name:
			continue
		if not frappe.db.exists("DocType", row.link_doctype):
			continue
		if frappe.has_permission(row.link_doctype, "read", row.link_name):
			visible.append(
				{"doctype": row.link_doctype, "docname": row.link_name, "title": row.link_title or row.link_name}
			)
	return visible


def _window(last_incoming: str | None) -> dict:
	if not last_incoming:
		return {"status": "unopened", "expires_at": None, "last_incoming_at": None}
	opened = get_datetime(last_incoming)
	expires = opened + WINDOW
	status = "open" if expires > now_datetime() else "closed"
	return {"status": status, "expires_at": expires.isoformat(), "last_incoming_at": opened.isoformat()}


def _window_from_messages(messages: list) -> dict:
	last = None
	for row in messages:
		if row.get("direction") == "Incoming" and not row.get("reaction"):
			last = row.get("creation")
	return _window(last)


def get_window_state(profile: str) -> dict:
	"""Return the 24-hour service window state for a given profile."""
	from nudg.integrations.site_store import last_incoming_at

	remote_at = last_incoming_at(profile)
	if remote_at is not None:
		return _window(remote_at or None)
	last_incoming = frappe.db.get_value(
		"WA Message",
		filters={"to": profile, "direction": "Incoming"},
		fieldname="creation",
		order_by="creation desc",
	)
	return _window(str(last_incoming) if last_incoming else None)


def _latest_activity(item: dict) -> str:
	"""Newest incoming or outgoing message. Chats with no message sort last."""
	preview = item.get("preview") or {}
	return str(preview.get("creation") or "")


def _unread_counts(profile_names: list[str]) -> dict[str, int]:
	"""Incoming messages the agent has not opened, per conversation."""
	if not profile_names or not frappe.db.has_column("WA Message", "status"):
		return {}
	from nudg.integrations.site_store import split_profiles, unread_counts

	local_names, remote_profiles = split_profiles(profile_names)
	remote_unread, remote_local = unread_counts(remote_profiles)
	local_names = list(local_names) + [name for name in remote_local if name not in local_names]
	if not local_names:
		return remote_unread
	profile_names = local_names
	reaction_clause = ""
	if frappe.db.has_column("WA Message", "reaction"):
		reaction_clause = "and ifnull(`reaction`, '') = ''"
	rows = frappe.db.sql(
		f"""
		select `to` as profile, count(*) as unread
		from `tabWA Message`
		where `to` in %(profiles)s
		  and direction = 'Incoming'
		  and ifnull(status, '') not in ('Read', 'Failed')
		  {reaction_clause}
		group by `to`
		""",
		{"profiles": profile_names},
		as_dict=True,
	)
	counts = {row.profile: int(row.unread or 0) for row in rows}
	counts.update(remote_unread)
	return counts


def _stamp(row):
	if not isinstance(row, frappe._dict):
		row = frappe._dict(row)
	row.creation = _iso(row.creation)
	row.is_template = bool(row.get("is_template"))
	if row.get("error_message"):
		row.error_message = format_error_message(row.error_message)
	return row


def publish_inbox_change(
	profile: str | None,
	message_name: str | None = None,
	bump: bool = False,
	message: dict | None = None,
) -> None:
	"""Push one conversation card the desk already computed.

	The browser inserts that card and, when present, the one changed message.
	It does not refetch the inbox. Failures are logged and never block the write
	that triggered the event.
	"""
	if not profile:
		return
	try:
		if not frappe.db.exists("DocType", "WA Message"):
			return
		card = _conversation_card(profile)
		if not card:
			return
		if message is None and message_name:
			message = _visible_message(message_name)
		elif message is not None:
			message = _stamp(message)
		frappe.publish_realtime(
			"nudg_inbox",
			{
				"profile": profile,
				"bump": bool(bump and message),
				"conversation": card,
				"message": message,
			},
			after_commit=True,
		)
	except Exception:
		frappe.log_error(title="Nudg inbox realtime", message=frappe.get_traceback())


def _conversation_card(profile_name: str) -> dict | None:
	rows = frappe.get_all(
		"WA Profile",
		filters={"name": profile_name},
		fields=_profile_fields(),
		limit_page_length=1,
	)
	if not rows:
		return None
	profile = rows[0]
	latest, incoming_at = _latest_previews([profile_name])
	preview = latest.get(profile_name)
	last_incoming = incoming_at.get(profile_name)
	try:
		assignment = assignments.get_conversation_map([profile_name]).get(profile_name) or {}
	except Exception:
		assignment = {}
	unread = _unread_counts([profile_name]).get(profile_name, 0)
	return _conversation_item(profile, preview, last_incoming, assignment, unread)


def _as_message(row):
	if not row:
		return None
	return _stamp(frappe._dict(row))


def _load_message(name: str | None):
	if not name:
		return None
	return _as_message(frappe.db.get_value("WA Message", name, MESSAGE_FIELDS, as_dict=True))


def _visible_message(name: str | None):
	"""The bubble this change should update. A reaction updates its parent message."""
	row = _load_message(name)
	if not row:
		return None
	if row.get("reaction") is not None and (row.get("context_message_id") or row.get("reply_to_message")):
		parent = _reaction_parent(row)
		if not parent:
			return None
		row = parent
	return _decorate_message(row)


def _reaction_parent(row):
	parent = _load_message(row.get("reply_to_message"))
	if parent and not parent.get("reaction"):
		return parent
	context = row.get("context_message_id")
	if not context:
		return None
	found = frappe.db.get_value("WA Message", {"message_id": context}, "name")
	parent = _load_message(found)
	if parent and not parent.get("reaction"):
		return parent
	return None


def _decorate_message(row):
	extras = [row]
	quoted = None
	if row.get("reply_to_message") and row.get("reply_to_message") != row.get("name"):
		quoted = _load_message(row.get("reply_to_message"))
	elif row.get("context_message_id"):
		found = frappe.db.get_value("WA Message", {"message_id": row.get("context_message_id")}, "name")
		quoted = _load_message(found)
	if quoted and quoted.get("name") != row.get("name"):
		extras.append(quoted)
	message_id = row.get("message_id")
	if message_id:
		reactions = frappe.get_all(
			"WA Message",
			filters={"context_message_id": message_id},
			fields=MESSAGE_FIELDS,
			limit_page_length=30,
		)
		for reaction in reactions:
			stamped = _as_message(reaction)
			if stamped and stamped.get("name") != row.get("name"):
				extras.append(stamped)
	folded = _fold(extras)
	_attach_templates(folded)
	for item in folded:
		if item.get("name") == row.get("name"):
			return item
	return row


def _iso(value) -> str | None:
	if not value:
		return None
	if isinstance(value, str):
		return get_datetime(value).isoformat()
	if hasattr(value, "isoformat"):
		return value.isoformat()
	return str(value)


def _clip(value: str | None, limit: int = 8000) -> str | None:
	if not value:
		return value
	text = str(value)
	if len(text) <= limit:
		return text
	return text[:limit] + "…"
