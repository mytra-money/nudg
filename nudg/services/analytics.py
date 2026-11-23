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

	from nudg.security import cache_get, cache_set

	user = getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	cache_key = f"nudg:analytics:{user}:{','.join(scoped)}"
	cached = cache_get(cache_key)
	if isinstance(cached, dict) and "messages_in" in cached:
		return cached

	day = getdate(today())
	account_filter = _account_clause(scoped)
	messages_in, messages_out, failed_messages = _message_totals(scoped, account_filter)
	open_conversations, unassigned = _profile_totals(scoped, account_filter)
	campaigns_sent = _campaign_totals(scoped, account_filter)

	data = {
		"snapshot_date": day,
		"messages_in": messages_in,
		"messages_out": messages_out,
		"failed_messages": failed_messages,
		"open_conversations": open_conversations,
		"unassigned": unassigned,
		"campaigns_sent": campaigns_sent,
		"has_accounts": True,
	}
	cache_set(cache_key, data, 60)
	return data


def _grouped(doctype: str, accounts: list[str], columns: list[str]) -> list | None:
	"""One grouped count for the permitted accounts. None when SQL is unavailable."""
	if not accounts or not columns:
		return None
	table = f"tab{doctype}"
	selected = ", ".join(f"`{column}`" for column in columns)
	try:
		rows = frappe.db.sql(
			f"""
			SELECT {selected}, COUNT(*) AS cnt
			FROM `{table}`
			WHERE `whatsapp_account` IN %(accounts)s
			GROUP BY {selected}
			""",
			{"accounts": tuple(accounts)},
			as_dict=True,
		)
	except Exception:
		return None
	return rows if isinstance(rows, list) else None


def _message_totals(accounts: list[str], account_filter: dict) -> tuple[int, int, int]:
	messages_in = messages_out = failed_messages = 0
	if not frappe.db.exists("DocType", "WA Message"):
		return messages_in, messages_out, failed_messages
	rows = _grouped("WA Message", accounts, ["direction", "status"])
	if rows is None:
		messages_in = frappe.db.count("WA Message", {**account_filter, "direction": "Incoming"})
		messages_out = frappe.db.count("WA Message", {**account_filter, "direction": "Outgoing"})
		failed_messages = frappe.db.count("WA Message", {**account_filter, "status": "Failed"})
		return messages_in, messages_out, failed_messages
	for row in rows:
		count = int(row.get("cnt") or 0)
		if row.get("direction") == "Incoming":
			messages_in += count
		elif row.get("direction") == "Outgoing":
			messages_out += count
		if row.get("status") == "Failed":
			failed_messages += count
	return messages_in, messages_out, failed_messages


def _profile_totals(accounts: list[str], account_filter: dict) -> tuple[int, int]:
	open_conversations = unassigned = 0
	native = _profile_totals_from_todos(accounts, account_filter)
	if native is not None:
		return native
	if not frappe.db.exists("DocType", "WA Profile"):
		return open_conversations, unassigned
	return open_conversations, unassigned


def _profile_totals_from_todos(accounts: list[str], account_filter: dict) -> tuple[int, int] | None:
	"""Open and unassigned chats from ToDo. None when that read is unavailable."""
	try:
		if not frappe.db.exists("DocType", "ToDo") or not frappe.db.exists("DocType", "WA Profile"):
			return None
		profiles = frappe.get_all(
			"WA Profile",
			filters=account_filter,
			pluck="name",
			limit_page_length=0,
		)
		if not isinstance(profiles, list):
			return None
		if not profiles:
			return 0, 0
		rows = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "WA Profile",
				"reference_name": ["in", profiles],
				"status": ["in", ["Open", "Closed"]],
			},
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
		closed_only = closed_names - open_names
		unassigned = max(len(profiles) - len(open_names) - len(closed_only), 0)
		return len(open_names) + unassigned, unassigned
	except Exception:
		return None


def _campaign_totals(accounts: list[str], account_filter: dict) -> int:
	if not frappe.db.exists("DocType", "WA Campaign"):
		return 0
	rows = _grouped("WA Campaign", accounts, ["status"])
	if rows is None:
		return frappe.db.count("WA Campaign", {**account_filter, "status": "Completed"})
	return sum(int(row.get("cnt") or 0) for row in rows if row.get("status") == "Completed")
