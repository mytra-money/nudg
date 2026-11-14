# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Chatbot and Agent Handoff integration for Nudg.

Softly coupled with `frappe_whatsapp_chatbot`: if the chatbot app is installed,
agent transfer and chatbot session handoffs are fully supported; if not,
the service safely degrades without errors.
"""

from __future__ import annotations

import frappe
from frappe import _
from nudg.utils.phone import normalize_mobile_no, phone_match_key


def is_chatbot_installed() -> bool:
	"""Check if frappe_whatsapp_chatbot is installed on this site."""
	try:
		return "frappe_whatsapp_chatbot" in frappe.get_installed_apps()
	except Exception:
		return False


def get_bot_status(phone_number: str, account: str | None = None) -> dict:
	"""Return active chatbot session and transfer status for a phone number."""
	if not is_chatbot_installed() or not phone_number:
		return {
			"installed": False,
			"has_bot_session": False,
			"is_transferred": False,
			"session": None,
			"transfer": None,
		}

	normalized = normalize_mobile_no(phone_number)
	key = phone_match_key(phone_number)

	filters: dict = {"status": "Active"}
	if account:
		filters["whatsapp_account"] = account

	# 1. Check active transfers
	transfers = frappe.get_all(
		"WhatsApp Agent Transfer",
		filters=filters,
		fields=["name", "phone_number", "whatsapp_account", "agent", "agent_name", "transferred_at", "notes"],
		order_by="transferred_at desc",
	)
	matched_transfer = None
	for tr in transfers:
		if phone_match_key(tr.phone_number) == key:
			matched_transfer = tr
			break

	# 2. Check active chatbot sessions
	sessions = frappe.get_all(
		"WhatsApp Chatbot Session",
		filters=filters,
		fields=["name", "phone_number", "whatsapp_account", "current_flow", "current_step", "started_at", "last_activity"],
		order_by="last_activity desc",
	)
	matched_session = None
	for s in sessions:
		if phone_match_key(s.phone_number) == key:
			matched_session = s
			break

	flow_title = None
	if matched_session and matched_session.get("current_flow"):
		flow_title = frappe.db.get_value("WhatsApp Chatbot Flow", matched_session.current_flow, "flow_name") or matched_session.current_flow

	return {
		"installed": True,
		"has_bot_session": bool(matched_session),
		"is_transferred": bool(matched_transfer),
		"session": matched_session,
		"flow_title": flow_title,
		"transfer": matched_transfer,
	}


def transfer_to_agent(phone_number: str, account: str | None = None, agent: str | None = None, notes: str | None = None) -> dict:
	"""Hand off a customer from chatbot to a human agent."""
	if not is_chatbot_installed():
		frappe.throw(_("Chatbot app is not installed on this site."), frappe.ValidationError)

	from frappe_whatsapp_chatbot.frappe_whatsapp_chatbot.doctype.whatsapp_agent_transfer.whatsapp_agent_transfer import (
		WhatsAppAgentTransfer,
	)

	agent = agent or frappe.session.user
	doc = WhatsAppAgentTransfer.transfer_to_agent(
		phone_number=phone_number,
		whatsapp_account=account,
		agent=agent,
		notes=notes,
	)
	return {"status": "transferred", "transfer": getattr(doc, "name", str(doc))}


def resume_chatbot(phone_number: str, account: str | None = None) -> dict:
	"""Resume automated chatbot for a conversation by resolving active agent transfers."""
	if not is_chatbot_installed():
		frappe.throw(_("Chatbot app is not installed on this site."), frappe.ValidationError)

	from frappe_whatsapp_chatbot.frappe_whatsapp_chatbot.doctype.whatsapp_agent_transfer.whatsapp_agent_transfer import (
		WhatsAppAgentTransfer,
	)

	WhatsAppAgentTransfer.resume_chatbot(
		phone_number=phone_number,
		whatsapp_account=account,
	)
	return {"status": "resumed"}
