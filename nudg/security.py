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


def _cache_enabled() -> bool:
	flags = getattr(getattr(frappe, "local", None), "flags", None)
	return not bool(getattr(flags, "in_test", False))


def cache_get(key: str):
	"""Redis value, or None when caching is off or the key is missing."""
	if not _cache_enabled():
		return None
	try:
		return frappe.cache().get_value(key, expires=True)
	except Exception:
		return None


def cache_set(key: str, value, ttl: int = 120) -> None:
	if not _cache_enabled():
		return
	try:
		frappe.cache().set_value(key, value, expires_in_sec=ttl)
	except Exception:
		return


def cache_delete_prefix(prefix: str) -> None:
	try:
		frappe.cache().delete_keys(prefix)
	except Exception:
		return


def clear_account_caches(user: str | None = None) -> None:
	"""Drop permission, account, template, and analytics caches."""
	if user:
		try:
			frappe.cache().delete_value(f"nudg:wa-accounts:{user}")
		except Exception:
			pass
		for prefix in (
			f"nudg:accounts-meta:{user}",
			f"nudg:analytics:{user}",
			f"nudg:templates:{user}",
		):
			cache_delete_prefix(prefix)
		return
	for prefix in ("nudg:wa-accounts", "nudg:accounts-meta", "nudg:analytics", "nudg:templates"):
		cache_delete_prefix(prefix)


def on_wa_account_change(doc=None, method=None) -> None:
	clear_account_caches()


def on_template_change(doc=None, method=None) -> None:
	cache_delete_prefix("nudg:templates")


def on_user_permission_change(doc=None, method=None) -> None:
	if getattr(doc, "allow", None) != "WA Account":
		return
	clear_account_caches(getattr(doc, "user", None))


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

	cache_key = f"nudg:wa-accounts:{user}"
	cached = cache_get(cache_key)
	if isinstance(cached, list):
		return list(cached)

	accounts = _query_user_wa_accounts(user)
	cache_set(cache_key, accounts, 120)
	return accounts


def _query_user_wa_accounts(user: str) -> list[str]:
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
		for acc in owned or []:
			if not isinstance(acc, str) or not acc.strip():
				continue
			if ensure_account_user_permission(acc, user):
				valid.append(acc)

	return valid


def get_assigned_wa_accounts(user: str | None = None) -> list[str]:
	"""Accounts given to this user, not every account an administrator can open.

	A User Permission or ownership counts. The System Manager "see all accounts"
	list does not, so someone with no number of their own stays on All numbers.
	"""
	if not frappe.db or not frappe.db.exists("DocType", "WA Account"):
		return []

	user = user or getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	if user in ("Guest", None, "Administrator"):
		return []

	names: list[str] = []
	permitted = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "WA Account"},
		pluck="for_value",
		order_by="for_value asc",
	)
	for acc in permitted or []:
		if acc and acc not in names and frappe.db.exists("WA Account", acc):
			names.append(acc)
	for acc in frappe.get_all("WA Account", filters={"owner": user}, pluck="name"):
		if acc and acc not in names:
			names.append(acc)
	return names


def undo_autoselected_default(doc, method=None) -> None:
	"""Leave WA Settings.default_account empty unless an admin set it.

	The official WA Account controller fills this field on insert whenever it is
	blank, so clearing it and then connecting another number puts that number
	back. Each client has their own number, so a new account must not claim the
	site fallback.
	"""
	name = getattr(doc, "name", None)
	if not name or not frappe.db.exists("DocType", "WA Settings"):
		return
	if frappe.db.get_single_value("WA Settings", "default_account") != name:
		return
	frappe.db.set_single_value("WA Settings", "default_account", "")


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
	if isinstance(roles, (list, tuple, set)) and "System Manager" in roles:
		return False

	if not isinstance(account, str):
		return False
	acc = account.strip()
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
	"""Limit inbox profiles to the WhatsApp accounts this user may see."""
	return _account_query_for("WA Profile", "whatsapp_account", user)


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


def _optional_account_query(doctype: str, user: str | None = None) -> str:
	"""Account filter that still shows rows with no account, such as a shared recipient list."""
	base = _account_query_for(doctype, "whatsapp_account", user)
	if not base or base == "1=0":
		return base
	return (
		f"({base} OR `tab{doctype}`.whatsapp_account IS NULL "
		f"OR `tab{doctype}`.whatsapp_account = '')"
	)


def get_tenant_bulk_query(user: str | None = None) -> str:
	return _account_query_for("WA Bulk Message", "whatsapp_account", user)


def get_tenant_recipient_list_query(user: str | None = None) -> str:
	return _optional_account_query("WA Recipient List", user)


def get_tenant_chatbot_query(user: str | None = None) -> str:
	return _account_query_for("WA Chatbot", "whatsapp_account", user)


def get_tenant_keyword_query(user: str | None = None) -> str:
	return _account_query_for("WA Keyword Reply", "whatsapp_account", user)


def get_tenant_flow_query(user: str | None = None) -> str:
	return _account_query_for("WA Chatbot Flow", "whatsapp_account", user)


def get_tenant_ai_context_query(user: str | None = None) -> str:
	return _account_query_for("WA AI Context", "whatsapp_account", user)


def get_tenant_session_query(user: str | None = None) -> str:
	return _account_query_for("WA Chatbot Session", "whatsapp_account", user)


def get_tenant_transfer_query(user: str | None = None) -> str:
	return _optional_account_query("WA Agent Transfer", user)


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
