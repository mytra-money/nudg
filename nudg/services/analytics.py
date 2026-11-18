"""Live inbox analytics computed from WA Message and WA Profile."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, today


def latest_snapshot(account: str | None = None) -> dict:
	return _live(account)


def list_snapshots(account: str | None = None, limit: int = 30) -> list[dict]:
	row = _live(account)
	if not row.get("has_accounts", True):
		return []
	return [row]


def resolve_accounts(account: str | None) -> list[str] | None:
	"""Accounts this user may include in analytics.

	``None`` means the user has no WhatsApp account, so callers must not query.
	A requested account outside that list is a permission error.
	"""
	from nudg.security import get_user_wa_accounts

	user = getattr(getattr(frappe, "session", None), "user", None)
	allowed = list(get_user_wa_accounts(user) or [])
	requested = (account or "").strip()
	if requested and requested.lower() != "all":
		if requested not in allowed:
			frappe.throw(
				_("You do not have access to this WhatsApp account."),
				frappe.PermissionError,
			)
		return [requested]
	if not allowed:
		return None
	return allowed


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


def _zeros() -> dict:
	return {
		"snapshot_date": getdate(today()),
		"messages_in": 0,
		"messages_out": 0,
		"failed_messages": 0,
		"open_conversations": 0,
		"unassigned": 0,
		"campaigns_sent": 0,
		"has_accounts": False,
	}


def _account_clause(accounts: list[str]) -> dict:
	if len(accounts) == 1:
		return {"whatsapp_account": accounts[0]}
	return {"whatsapp_account": ["in", accounts]}


def _compute(account: str | None) -> dict:
	scoped = resolve_accounts(account)
	if not scoped:
		return _zeros()

	day = getdate(today())
	account_filter = _account_clause(scoped)
	messages_in = messages_out = failed_messages = 0
	if frappe.db.exists("DocType", "WA Message"):
		messages_in = frappe.db.count("WA Message", {**account_filter, "direction": "Incoming"})
		messages_out = frappe.db.count("WA Message", {**account_filter, "direction": "Outgoing"})
		failed_messages = frappe.db.count("WA Message", {**account_filter, "status": "Failed"})

	open_conversations = unassigned = 0
	if frappe.db.exists("DocType", "WA Profile") and frappe.db.has_column("WA Profile", "assignment_status"):
		open_conversations = frappe.db.count(
			"WA Profile",
			{**account_filter, "assignment_status": ["in", ["Unassigned", "Assigned"]]},
		)
		unassigned = frappe.db.count(
			"WA Profile", {**account_filter, "assignment_status": "Unassigned"}
		)

	campaigns_sent = 0
	if frappe.db.exists("DocType", "UTM Campaign"):
		campaigns_sent = frappe.db.count(
			"UTM Campaign", {**account_filter, "whatsapp_status": "Completed"}
		)

	return {
		"snapshot_date": day,
		"messages_in": messages_in,
		"messages_out": messages_out,
		"failed_messages": failed_messages,
		"open_conversations": open_conversations,
		"unassigned": unassigned,
		"campaigns_sent": campaigns_sent,
		"has_accounts": True,
	}
