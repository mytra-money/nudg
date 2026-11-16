# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""User Permission Scoping on WA Account (Single Source of Truth).

Scoping directly on WA Account:
- When a user configures a WA Account, a standard User Permission is applied to them.
- All conversations, messages, templates, campaigns, and team members are scoped
  to the user's permitted WA Account(s).
- Administrator and System Manager have access across all accounts.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _


def _get_roles(user: str) -> set[str]:
	if not user or user == "Guest":
		return set()
	if user == "Administrator":
		return {"Administrator", "System Manager"}
	try:
		if getattr(frappe, "cache", None):
			return set(frappe.get_roles(user))
	except Exception:
		pass
	try:
		if getattr(frappe, "db", None):
			return set(frappe.get_all("Has Role", filters={"parent": user}, pluck="role"))
	except Exception:
		pass
	return set()


def get_user_wa_accounts(user: str | None = None) -> list[str]:
	"""Return list of WA Account names the user is permitted to access.

	Administrator / System Manager can access all active accounts.
	Standard users can only access accounts granted via standard Frappe User Permission.
	"""
	if not frappe.db or not frappe.db.exists("DocType", "WA Account"):
		return []

	user = user or getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	if user in ("Guest", None):
		return []

	roles = _get_roles(user)
	if user == "Administrator" or "System Manager" in roles:
		return frappe.get_all(
			"WA Account",
			pluck="name",
			order_by="account_name asc",
		)

	# Fetch explicit User Permissions on WA Account
	accounts = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "WA Account"},
		pluck="for_value",
		order_by="for_value asc",
	)

	valid = []
	for acc in accounts or []:
		if acc and frappe.db.exists("WA Account", acc):
			valid.append(acc)

	# If the user has no explicit user permission yet, but is creator/owner of accounts
	if not valid:
		owned = frappe.get_all(
			"WA Account",
			filters={"owner": user},
			pluck="name",
		)
		for acc in owned:
			ensure_account_user_permission(acc, user)
			valid.append(acc)

	return valid


def get_default_account(user: str | None = None) -> str | None:
	"""Return default WA Account for the user."""
	user_accounts = get_user_wa_accounts(user)
	if not user_accounts:
		return None

	# Check global default in WA Settings
	if frappe.db.exists("DocType", "WA Settings"):
		default_acc = frappe.db.get_single_value("WA Settings", "default_account")
		if default_acc and default_acc in user_accounts:
			return default_acc

	return user_accounts[0]


def is_account_manager(account: str, user: str | None = None) -> bool:
	"""Check if user has management permissions over a WA Account."""
	user = user or getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	if user in ("Guest", None):
		return False

	roles = _get_roles(user)
	if user == "Administrator" or "System Manager" in roles:
		return True

	if not account or not frappe.db.exists("WA Account", account):
		return False

	owner = frappe.db.get_value("WA Account", account, "owner")
	if owner and owner == user:
		return True

	if "WhatsApp Manager" in roles:
		return account in get_user_wa_accounts(user)

	return False


def on_user_created(doc, method=None):
	"""Leave new users alone.

	WhatsApp Manager is granted when someone creates a WA Account, and team
	APIs set WhatsApp User or WhatsApp Manager explicitly. Auto-promoting every
	ERPNext user would give the whole company the desk manager role.
	"""
	return


def ensure_account_user_permission(account: str, user: str | None = None) -> bool:
	"""Grant standard Frappe User Permission for a WA Account to a user."""
	user = user or getattr(getattr(frappe, "session", None), "user", None)
	if not user or user in ("Guest", "Administrator"):
		return False

	roles = _get_roles(user)
	if "System Manager" in roles:
		return False

	acc = (account or "").strip()
	if not acc or not frappe.db.exists("WA Account", acc):
		return False

	existing = frappe.db.exists(
		"User Permission",
		{"user": user, "allow": "WA Account", "for_value": acc},
	)
	if existing:
		return True

	doc = frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": "WA Account",
			"for_value": acc,
			"apply_to_all_doctypes": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return True


# -----------------------------------------------------------------------------
# Row-Level Security Condition Builders (for hooks.py permission_query_conditions)
# -----------------------------------------------------------------------------

def _account_query_for(doctype: str, fieldname: str = "whatsapp_account", user: str | None = None) -> str:
	user = user or getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	if user in ("Guest", None):
		return "1=0"

	roles = _get_roles(user)
	if user == "Administrator" or "System Manager" in roles:
		return ""

	accounts = get_user_wa_accounts(user)
	if not accounts:
		return "1=0"

	escaped = ", ".join(frappe.db.escape(a) for a in accounts)
	return f"`tab{doctype}`.{fieldname} IN ({escaped})"


def get_tenant_conversation_query(user: str | None = None) -> str:
	return _account_query_for("WA Conversation", "whatsapp_account", user)


def get_tenant_campaign_query(user: str | None = None) -> str:
	user = user or getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	if user in ("Guest", None):
		return "1=0"

	roles = _get_roles(user)
	if user == "Administrator" or "System Manager" in roles:
		return ""

	accounts = get_user_wa_accounts(user)
	if not accounts:
		return "(`tabUTM Campaign`.whatsapp_account IS NULL OR `tabUTM Campaign`.whatsapp_account = '')"

	escaped = ", ".join(frappe.db.escape(a) for a in accounts)
	return f"(`tabUTM Campaign`.whatsapp_account IN ({escaped}) OR `tabUTM Campaign`.whatsapp_account IS NULL OR `tabUTM Campaign`.whatsapp_account = '')"


def get_tenant_rule_query(user: str | None = None) -> str:
	return _account_query_for("WA Automation Rule", "whatsapp_account", user)


def get_tenant_hours_query(user: str | None = None) -> str:
	return ""


def get_tenant_quick_reply_query(user: str | None = None) -> str:
	user = user or getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	if user == "Administrator" or "System Manager" in _get_roles(user):
		return ""
	accounts = get_user_wa_accounts(user)
	if not accounts:
		return "1=0"
	escaped = ", ".join(frappe.db.escape(a) for a in accounts)
	return f"(`tabWA Quick Reply`.whatsapp_account IN ({escaped}) OR `tabWA Quick Reply`.whatsapp_account IS NULL OR `tabWA Quick Reply`.whatsapp_account = '')"


def get_tenant_catalog_query(user: str | None = None) -> str:
	return _account_query_for("WA Catalog", "whatsapp_account", user)


# -----------------------------------------------------------------------------
# Document-Level Permission Checkers (for hooks.py has_permission)
# -----------------------------------------------------------------------------

def has_tenant_permission(doc: Any, ptype: str = "read", user: str | None = None) -> bool:
	"""Document-level check enforcing WA Account boundary on a single doc."""
	user = user or getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	if user == "Administrator" or "System Manager" in _get_roles(user):
		return True

	if hasattr(doc, "doctype") and doc.doctype == "WA Account":
		return doc.name in get_user_wa_accounts(user)

	doc_acc = getattr(doc, "whatsapp_account", None) or getattr(doc, "wa_account", None) or getattr(doc, "channel", None)
	if not doc_acc:
		return True

	return doc_acc in get_user_wa_accounts(user)
