# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Desk API for connecting an ERPNext site. The Notification rule stays on that site."""

from __future__ import annotations

import frappe
from frappe import _

from nudg.integrations.erpnext.payload import PayloadError
from nudg.integrations.erpnext.service import connect_site as connect_site_record
from nudg.integrations.erpnext.service import set_site_enabled as set_site_enabled_record
from nudg.security import get_user_wa_accounts


def _manager() -> None:
	if frappe.session.user in (None, "Guest"):
		frappe.throw(_("Log in to connect ERPNext."), frappe.PermissionError)
	roles = set(frappe.get_roles())
	if frappe.session.user != "Administrator" and not roles.intersection({"System Manager", "WhatsApp Manager"}):
		frappe.throw(_("Only a WhatsApp manager can connect ERPNext."), frappe.PermissionError)


def _allowed_accounts() -> list[str] | None:
	roles = set(frappe.get_roles())
	if frappe.session.user == "Administrator" or "System Manager" in roles:
		return None
	return get_user_wa_accounts()


@frappe.whitelist()
def list_sites() -> list[dict]:
	_manager()
	if not frappe.db.exists("DocType", "Connected Site"):
		return []
	rows = frappe.get_list(
		"Connected Site",
		fields=["name", "site_url", "status", "whatsapp_account", "remote_user", "last_error", "modified"],
		order_by="modified desc",
		limit_page_length=50,
	)
	allowed = _allowed_accounts()
	if allowed is None:
		return rows
	return [row for row in rows if row.whatsapp_account in allowed]


@frappe.whitelist()
def connect_site(site_name: str, site_url: str, api_key: str, api_secret: str, whatsapp_account: str) -> dict:
	_manager()
	allowed = _allowed_accounts()
	if allowed is not None and whatsapp_account not in allowed:
		frappe.throw(_("You cannot connect ERPNext to that WhatsApp account."), frappe.PermissionError)
	try:
		return connect_site_record(site_name, site_url, api_key, api_secret, whatsapp_account)
	except PayloadError as exc:
		frappe.throw(str(exc))


@frappe.whitelist()
def set_site_enabled(site: str, enabled: int | str = 1) -> dict:
	_manager()
	doc = frappe.get_doc("Connected Site", site)
	allowed = _allowed_accounts()
	if allowed is not None and doc.whatsapp_account not in allowed:
		frappe.throw(_("You cannot change that ERPNext site."), frappe.PermissionError)
	flag = str(enabled) not in {"0", "false", "False"}
	return set_site_enabled_record(site, flag)
