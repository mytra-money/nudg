# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""WhatsApp Business app coexistence.

A number that stays on the Business app is not registered again. After connect,
Meta sends contacts, up to six months of 1:1 history, and later echoes of
messages the business sends from the phone. Those copies are stored as chat
history and do not run the chatbot.
"""

from __future__ import annotations

import time
from typing import Any

import frappe

HISTORY_DECLINED = 2593109
PLACEHOLDER = "[Media]"
_SMB_PLATFORMS = {"SMB", "SMB_CLOUD_API"}
_STATUS = {
	"sent": "Sent",
	"delivered": "Delivered",
	"read": "Read",
	"played": "Read",
	"pending": "Pending",
	"error": "Failed",
	"failed": "Failed",
}


def on_business_app(is_on_biz_app: Any, platform_type: str | None, signup_event: bool = False) -> bool:
	"""True when this number should stay on the Business app and skip Cloud API registration."""
	if signup_event:
		return True
	if is_on_biz_app in (True, 1, "1", "true", "True"):
		return True
	return str(platform_type or "").upper() in _SMB_PLATFORMS


def parse_history(value: dict) -> dict:
	"""Threads and a later media follow-up from one history webhook."""
	declined = False
	progress = None
	messages: list[dict] = []
	business = _digits(((value or {}).get("metadata") or {}).get("display_phone_number"))
	for block in (value or {}).get("history") or []:
		if not isinstance(block, dict):
			continue
		for error in block.get("errors") or []:
			if isinstance(error, dict) and _code(error.get("code")) == HISTORY_DECLINED:
				declined = True
		meta = block.get("metadata") or {}
		if meta.get("progress") is not None:
			progress = _code(meta.get("progress"))
		for thread in block.get("threads") or []:
			if not isinstance(thread, dict):
				continue
			customer = str(thread.get("id") or "")
			for msg in thread.get("messages") or []:
				if isinstance(msg, dict):
					messages.append(_message_row(msg, customer, follow_up=False))
	for msg in (value or {}).get("messages") or []:
		if isinstance(msg, dict):
			messages.append(_message_row(msg, str(msg.get("from") or ""), follow_up=True))
	return {"declined": declined, "progress": progress, "business": business, "messages": messages}


def parse_echoes(value: dict) -> list[dict]:
	"""Messages the business sent from the phone after onboarding."""
	rows = []
	for msg in (value or {}).get("message_echoes") or []:
		if not isinstance(msg, dict) or not msg.get("id"):
			continue
		rows.append(_message_row(msg, str(msg.get("to") or ""), follow_up=False, outgoing=True))
	return rows


def parse_contacts(value: dict) -> list[dict]:
	rows = []
	for item in (value or {}).get("state_sync") or []:
		if not isinstance(item, dict) or item.get("type") != "contact":
			continue
		contact = item.get("contact") or {}
		phone = str(contact.get("phone_number") or "")
		if not phone:
			continue
		rows.append({
			"action": item.get("action") or "add",
			"phone": phone,
			"name": contact.get("full_name") or contact.get("first_name") or phone,
		})
	return rows


def pace(account: str) -> None:
	"""Coexistence numbers are fixed at 20 messages a second."""
	if not account or not _flag(account, "coexistence"):
		return
	now = time.monotonic()
	key = f"nudg:coexistence:mps:{account}"
	try:
		stamps = [float(item) for item in (frappe.cache().get_value(key) or [])]
	except Exception:
		return
	stamps = [item for item in stamps if now - item < 1]
	if len(stamps) >= 20:
		time.sleep(max(0.0, 1 - (now - stamps[0])))
		now = time.monotonic()
		stamps = [item for item in stamps if now - item < 1]
	stamps.append(now)
	try:
		frappe.cache().set_value(key, stamps, expires_in_sec=2)
	except Exception:
		return


def start_sync(phone_number_id: str, token: str, version: str, account: str) -> list[str]:
	"""Ask Meta for contacts, then history. Each call can be made only once."""
	from nudg.integrations.embedded_signup import EmbeddedSignupError, _graph

	warnings: list[str] = []
	for sync_type in ("smb_app_state_sync", "history"):
		try:
			_graph(
				"POST",
				f"https://graph.facebook.com/{version}/{phone_number_id}/smb_app_data",
				token=token,
				payload={"messaging_product": "whatsapp", "sync_type": sync_type},
			)
		except EmbeddedSignupError as exc:
			warnings.append(str(exc))
	if warnings:
		_set_sync(account, "Error", " ".join(warnings))
	else:
		_set_sync(account, "Syncing", "")
	return warnings


def consume(payload: dict | None) -> None:
	"""Store Business-app webhooks. Unknown fields are left for the message handler."""
	if not isinstance(payload, dict):
		return
	try:
		for entry in payload.get("entry") or []:
			if not isinstance(entry, dict):
				continue
			for change in entry.get("changes") or []:
				if not isinstance(change, dict):
					continue
				_consume_change(str(entry.get("id") or ""), change)
	except Exception:
		frappe.log_error(title="WhatsApp Business app sync")


def _consume_change(waba_id: str, change: dict) -> None:
	field = change.get("field")
	value = change.get("value") or {}
	if field == "account_update":
		_disconnect(waba_id, value)
		return
	if field not in ("history", "smb_app_state_sync", "smb_message_echoes"):
		return
	from nudg.integrations.site_store import account_for_phone

	phone_id = ((value.get("metadata") or {}).get("phone_number_id"))
	account = account_for_phone(phone_id)
	if not account:
		return
	if field == "history":
		_take_history(account, value)
	elif field == "smb_app_state_sync":
		_take_contacts(account, value)
	else:
		for row in parse_echoes(value):
			save_message(account, row)


def _take_history(account: str, value: dict) -> None:
	parsed = parse_history(value)
	if parsed["declined"]:
		_set_sync(account, "Declined", "The business did not share WhatsApp Business app history.")
		return
	for row in parsed["messages"]:
		save_message(account, row)
	progress = parsed["progress"]
	if progress is None:
		return
	_set_progress(account, progress)
	if progress >= 100 and _sync_status(account) != "Declined":
		_set_sync(account, "Synced", "")


def _take_contacts(account: str, value: dict) -> None:
	for row in parse_contacts(value):
		if row["action"] == "remove":
			continue
		_ensure_profile(account, row["phone"], row["name"])


def save_message(account: str, row: dict) -> None:
	"""Write one mirrored message on the account's site, or here if that site is down."""
	if not row.get("message_id") or not row.get("customer"):
		return
	from nudg.integrations.site_store import _client_delivery

	if _client_delivery(account) and _save_remote(account, row):
		return
	_save_local(account, row, pending=_client_delivery(account))


def _save_remote(account: str, row: dict) -> bool:
	from nudg.integrations.site_store import RemoteStore

	try:
		return RemoteStore.for_delivery(account).save_mirror(row)
	except Exception:
		frappe.log_error(title="WhatsApp Business app remote copy")
		return False


def _save_local(account: str, row: dict, pending: bool) -> None:
	message_id = str(row["message_id"])
	try:
		existing = frappe.db.get_value("WA Message", {"message_id": message_id}, ["name", "message"], as_dict=True)
	except Exception:
		existing = None
	if isinstance(existing, dict) and existing.get("name"):
		if _should_fill(existing.get("message"), row.get("content")):
			frappe.db.set_value(
				"WA Message",
				existing["name"],
				{"message": row.get("content") or ""},
				update_modified=False,
			)
		return
	profile = _ensure_profile(account, row["customer"], row["customer"])
	if not profile:
		return
	doc = frappe.get_doc({
		"doctype": "WA Message",
		"to": profile,
		"from": row["customer"] if row.get("direction") == "Incoming" else "",
		"message": row.get("content") or "",
		"whatsapp_account": account,
		"direction": row.get("direction") or "Incoming",
		"status": row.get("status") or "Sent",
		"message_id": message_id,
		"timestamp": _timestamp(row.get("timestamp")),
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_chatbot = True
	doc.flags.nudg_mirrored = True
	doc.flags.nudg_skip_client_sync = True
	if pending and _has_field("WA Message", "client_sync"):
		doc.client_sync = "Pending"
	try:
		doc.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="WhatsApp Business app message")
		return
	if row.get("direction") == "Outgoing":
		try:
			frappe.db.set_value("WA Message", doc.name, "docstatus", 1, update_modified=False)
		except Exception:
			frappe.log_error(title="WhatsApp Business app message")


def _ensure_profile(account: str, phone: str, name: str) -> str | None:
	from nudg.integrations.site_store import _client_delivery, _display_phone
	from nudg.integrations.whatsapp import adapter

	display = _display_phone(phone)
	if _client_delivery(account):
		try:
			remote = RemoteProfile(account).ensure(display, name)
			if remote:
				adapter.ensure_local_profile(display, account, profile_name=name or None)
				return remote
		except Exception:
			frappe.log_error(title="WhatsApp Business app contact")
	return adapter.ensure_local_profile(display, account, profile_name=name or None)


class RemoteProfile:
	"""Profile create on the client site, used while that site is the store."""

	def __init__(self, account: str):
		self.account = account

	def ensure(self, phone: str, name: str) -> str:
		from nudg.integrations.site_store import RemoteStore

		return RemoteStore.for_delivery(self.account).ensure_profile(phone, name)


def _disconnect(waba_id: str, value: dict) -> None:
	if (value or {}).get("event") != "PARTNER_REMOVED" or not waba_id:
		return
	try:
		rows = frappe.get_all(
			"WA Account",
			filters={"business_id": waba_id},
			fields=["name", "account_name"],
		)
	except Exception:
		return
	phone = _digits((value or {}).get("phone_number"))
	matched = [row for row in rows if phone and phone in _digits(row.get("account_name"))]
	targets = matched or (rows if len(rows) == 1 else [])
	for row in targets:
		_set_sync(row["name"], "Error", "Disconnected in the WhatsApp Business app.")


def _message_row(msg: dict, customer: str, follow_up: bool, outgoing: bool = False) -> dict:
	kind = msg.get("type") or "text"
	if outgoing:
		direction = "Outgoing"
	elif follow_up:
		direction = "Incoming"
	else:
		direction = "Incoming" if _digits(msg.get("from")) == _digits(customer) else "Outgoing"
	status = "Sent"
	context = msg.get("history_context") or {}
	if context.get("status"):
		status = _STATUS.get(str(context.get("status")).lower(), "Sent")
	return {
		"customer": customer,
		"message_id": msg.get("id"),
		"content": _content(msg),
		"direction": direction,
		"status": status,
		"timestamp": msg.get("timestamp"),
		"placeholder": kind == "media_placeholder",
		"fill_only": follow_up,
	}


def _content(msg: dict) -> str:
	kind = msg.get("type") or "text"
	if kind == "media_placeholder":
		return PLACEHOLDER
	if kind == "text":
		return ((msg.get("text") or {}).get("body")) or ""
	body = msg.get(kind) or {}
	if isinstance(body, dict) and body.get("caption"):
		return str(body.get("caption"))
	if kind in ("image", "audio", "video", "document", "sticker"):
		return f"[{kind}]"
	return ""


def _should_fill(current: str | None, new: str | None) -> bool:
	if not new or new == PLACEHOLDER:
		return False
	return not current or current == PLACEHOLDER


def _set_sync(account: str, status: str, error: str) -> None:
	if not account or not _has_field("WA Account", "coexistence_sync"):
		return
	values = {"coexistence_sync": status}
	if _has_field("WA Account", "coexistence_error"):
		values["coexistence_error"] = (error or "")[:1000]
	try:
		frappe.db.set_value("WA Account", account, values, update_modified=False)
	except Exception:
		frappe.log_error(title="WhatsApp Business app sync")


def _set_progress(account: str, progress: int) -> None:
	if not _has_field("WA Account", "coexistence_progress"):
		return
	try:
		frappe.db.set_value("WA Account", account, "coexistence_progress", int(progress), update_modified=False)
	except Exception:
		frappe.log_error(title="WhatsApp Business app sync")


def _sync_status(account: str) -> str:
	if not _has_field("WA Account", "coexistence_sync"):
		return ""
	try:
		return str(frappe.db.get_value("WA Account", account, "coexistence_sync") or "")
	except Exception:
		return ""


def _flag(account: str, field: str) -> bool:
	if not _has_field("WA Account", field):
		return False
	try:
		return bool(frappe.db.get_value("WA Account", account, field))
	except Exception:
		return False


def _has_field(doctype: str, field: str) -> bool:
	try:
		return bool(frappe.get_meta(doctype).has_field(field))
	except Exception:
		return False


def _timestamp(raw) -> str | None:
	from nudg.integrations.site_store import _timestamp as site_timestamp

	if not raw:
		return None
	return site_timestamp(raw)


@frappe.whitelist()
def save_on_client(doc: dict | str) -> str:
	"""Store a mirrored message on this site without running the chatbot."""
	if frappe.session.user in (None, "Guest"):
		frappe.throw("Log in to store a WhatsApp message.", frappe.PermissionError)
	if isinstance(doc, str):
		import json

		doc = json.loads(doc)
	if not isinstance(doc, dict) or not doc.get("message_id"):
		frappe.throw("A WhatsApp message is required.")
	existing = frappe.db.get_value("WA Message", {"message_id": doc.get("message_id")}, "name")
	if existing:
		return str(existing)
	message = frappe.get_doc(doc)
	message.flags.ignore_permissions = True
	message.flags.ignore_chatbot = True
	message.flags.nudg_mirrored = True
	message.flags.nudg_skip_client_sync = True
	message.insert(ignore_permissions=True)
	if message.direction == "Outgoing":
		frappe.db.set_value("WA Message", message.name, "docstatus", 1, update_modified=False)
	return message.name


def _digits(value: Any) -> str:
	return "".join(ch for ch in str(value or "") if ch.isdigit())


def _code(value: Any) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return 0
