"""Live inbox analytics computed from WA Message and WA Conversation."""

from __future__ import annotations

import frappe
from frappe.utils import getdate, now_datetime, today


def latest_snapshot(account: str | None = None) -> dict:
	return _live(account)


def list_snapshots(account: str | None = None, limit: int = 30) -> list[dict]:
	return [_live(account)]


def refreshing_snapshot(account: str | None = None) -> dict | None:
	return None


def enqueue_refresh(account: str | None = None) -> dict:
	return _live(account)


def daily_snapshot():
	"""Kept so older scheduler entries do not fail after the snapshot DocType was removed."""
	return None


def _live(account: str | None) -> dict:
	data = _compute(account)
	data.update(
		{
			"name": "live",
			"whatsapp_account": account,
			"status": "Ready",
			"generated_at": now_datetime(),
			"error_message": None,
		}
	)
	return data


def _compute(account: str | None) -> dict:
	day = getdate(today())
	msg_filters: dict = {}
	if account and frappe.db.exists("DocType", "WA Message"):
		msg_filters["whatsapp_account"] = account

	messages_in = messages_out = failed_messages = 0
	if frappe.db.exists("DocType", "WA Message"):
		messages_in = frappe.db.count("WA Message", {**msg_filters, "direction": "Incoming"})
		messages_out = frappe.db.count("WA Message", {**msg_filters, "direction": "Outgoing"})
		failed_messages = frappe.db.count("WA Message", {**msg_filters, "status": "Failed"})

	open_conversations = unassigned = 0
	if frappe.db.exists("DocType", "WA Conversation"):
		conv_filters = {}
		if account:
			conv_filters["whatsapp_account"] = account
		open_conversations = frappe.db.count(
			"WA Conversation", {**conv_filters, "assignment_status": ["in", ["Unassigned", "Assigned"]]}
		)
		unassigned = frappe.db.count(
			"WA Conversation", {**conv_filters, "assignment_status": "Unassigned"}
		)

	campaigns_sent = 0
	if frappe.db.exists("DocType", "UTM Campaign"):
		camp_filters = {"whatsapp_status": "Completed"}
		if account:
			camp_filters["whatsapp_account"] = account
		campaigns_sent = frappe.db.count("UTM Campaign", camp_filters)

	return {
		"snapshot_date": day,
		"messages_in": messages_in,
		"messages_out": messages_out,
		"failed_messages": failed_messages,
		"open_conversations": open_conversations,
		"unassigned": unassigned,
		"campaigns_sent": campaigns_sent,
	}
