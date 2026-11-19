# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Chatbot status and agent handoff for the Nudg inbox.

The bot runs inside Nudg. It does not call frappe_whatsapp_chatbot.
"""

from __future__ import annotations

import frappe
from frappe import _

from nudg.utils.phone import phone_match_key


def is_chatbot_installed() -> bool:
	"""True when the native chatbot DocType is on this site."""
	try:
		return bool(frappe.db.exists("DocType", "WA Chatbot"))
	except Exception:
		return False


def get_settings(account: str | None):
	"""The chatbot document for one WhatsApp account, or None."""
	if not account or not is_chatbot_installed():
		return None
	try:
		name = account if frappe.db.exists("WA Chatbot", account) else None
		if not name:
			name = frappe.db.get_value("WA Chatbot", {"whatsapp_account": account}, "name")
		return frappe.get_doc("WA Chatbot", name) if name else None
	except Exception:
		frappe.log_error(title="Chatbot settings could not be read")
		return None


def is_enabled(account: str | None = None) -> bool:
	"""True when this account has an enabled chatbot. With no account, true if any are enabled."""
	if not is_chatbot_installed():
		return False
	try:
		if account:
			return bool(frappe.db.get_value("WA Chatbot", {"whatsapp_account": account}, "enabled"))
		return bool(frappe.db.get_value("WA Chatbot", {"enabled": 1}, "name"))
	except Exception:
		return False


def get_bot_status(phone_number: str, account: str | None = None) -> dict:
	"""Active session and agent transfer for a customer number."""
	empty = {
		"installed": is_chatbot_installed(),
		"enabled": False,
		"has_bot_session": False,
		"is_transferred": False,
		"session": None,
		"transfer": None,
	}
	if not phone_number or not empty["installed"]:
		return empty
	empty["enabled"] = is_enabled(account)
	key = phone_match_key(phone_number)

	transfer = _match_phone("WA Agent Transfer", key, account, [
		"name", "phone_number", "whatsapp_account", "agent", "agent_name", "transferred_at", "notes",
	])
	session = _match_phone("WA Chatbot Session", key, account, [
		"name", "phone_number", "whatsapp_account", "current_flow", "current_step", "started_at", "last_activity",
	])
	flow_title = None
	if session and session.get("current_flow"):
		flow_title = frappe.db.get_value("WA Chatbot Flow", session.current_flow, "flow_name") or session.current_flow
	empty.update({
		"has_bot_session": bool(session),
		"is_transferred": bool(transfer),
		"session": session,
		"flow_title": flow_title,
		"transfer": transfer,
	})
	return empty


def transfer_to_agent(phone_number: str, account: str | None = None, agent: str | None = None, notes: str | None = None) -> dict:
	"""Pause the bot and record the human handoff."""
	if not is_chatbot_installed():
		frappe.throw(_("The chatbot is not available on this site."), frappe.ValidationError)
	from nudg.nudg.doctype.wa_agent_transfer.wa_agent_transfer import WAAgentTransfer

	doc = WAAgentTransfer.transfer_to_agent(
		phone_number=phone_number,
		whatsapp_account=account,
		agent=agent or frappe.session.user,
		notes=notes,
	)
	return {"status": "transferred", "transfer": doc.name, "name": doc.name}


@frappe.whitelist()
def is_transferred(phone_number: str, whatsapp_account: str | None = None) -> dict:
	"""Whether the bot is paused for this number."""
	if not phone_number:
		frappe.throw(_("Phone number is required."))
	frappe.has_permission("WA Agent Transfer", "read", throw=True)
	from nudg.nudg.doctype.wa_agent_transfer.wa_agent_transfer import WAAgentTransfer

	name = WAAgentTransfer.is_transferred(phone_number, whatsapp_account)
	if not name:
		return {"is_transferred": False, "phone_number": phone_number}
	transfer = frappe.get_doc("WA Agent Transfer", name)
	return {
		"is_transferred": True,
		"phone_number": phone_number,
		"transfer_name": transfer.name,
		"agent": transfer.agent,
		"agent_name": transfer.agent_name,
		"transferred_at": transfer.transferred_at,
	}


@frappe.whitelist()
def get_active_transfers(whatsapp_account: str | None = None, agent: str | None = None) -> list[dict]:
	"""Active human handoffs."""
	frappe.has_permission("WA Agent Transfer", "read", throw=True)
	filters = {"status": "Active"}
	if whatsapp_account:
		filters["whatsapp_account"] = whatsapp_account
	if agent:
		filters["agent"] = agent
	return frappe.get_all(
		"WA Agent Transfer",
		filters=filters,
		fields=["name", "phone_number", "whatsapp_account", "agent", "agent_name", "transferred_at", "notes"],
		order_by="transferred_at desc",
	)


def resume_chatbot(phone_number: str, account: str | None = None) -> dict:
	"""Let the bot reply again."""
	if not is_chatbot_installed():
		frappe.throw(_("The chatbot is not available on this site."), frappe.ValidationError)
	from nudg.nudg.doctype.wa_agent_transfer.wa_agent_transfer import WAAgentTransfer

	resumed = WAAgentTransfer.resume_chatbot(phone_number=phone_number, whatsapp_account=account)
	return {"status": "resumed" if resumed else "not_found", "resumed": bool(resumed)}


def _match_phone(doctype: str, key: str, account: str | None, fields: list[str]):
	if not frappe.db.exists("DocType", doctype):
		return None
	filters = {"status": "Active"}
	if account:
		filters["whatsapp_account"] = account
	rows = frappe.get_all(doctype, filters=filters, fields=fields, order_by="modified desc", limit_page_length=50)
	for row in rows:
		if phone_match_key(row.phone_number) == key:
			return row
	return None
