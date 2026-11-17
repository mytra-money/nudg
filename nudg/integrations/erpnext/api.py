# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Desk API for connecting an ERPNext site. The Notification rule stays on that site."""

from __future__ import annotations

import frappe
from frappe import _

from nudg.integrations.erpnext.alerts import (
	create_alert as create_alert_record,
	delete_alert as delete_alert_record,
	describe_doctype,
	list_alerts as list_alert_records,
	list_doctypes,
	list_templates,
	set_alert_enabled as set_alert_enabled_record,
)
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
	if not frappe.db.exists("DocType", "WA Account"):
		return []
	if not frappe.db.has_column("WA Account", "erp_site_name"):
		return []
	rows = frappe.get_list(
		"WA Account",
		filters={"erp_site_name": ["is", "set"]},
		fields=[
			"name",
			"erp_site_name",
			"erp_site_url",
			"erp_status",
			"erp_remote_user",
			"erp_last_error",
			"modified",
		],
		order_by="modified desc",
		limit_page_length=50,
	)
	allowed = _allowed_accounts()
	public = []
	for row in rows:
		if allowed is not None and row.name not in allowed:
			continue
		public.append(
			{
				"name": row.name,
				"site_name": row.erp_site_name,
				"site_url": row.erp_site_url,
				"status": row.erp_status,
				"whatsapp_account": row.name,
				"remote_user": row.erp_remote_user,
				"last_error": row.erp_last_error,
				"modified": row.modified,
			}
		)
	return public


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
	from nudg.integrations.erpnext.service import _load_site

	doc = _load_site(site)
	if doc is None:
		frappe.throw(_("Connect the ERPNext site first."))
	allowed = _allowed_accounts()
	if allowed is not None and doc.whatsapp_account not in allowed:
		frappe.throw(_("You cannot change that ERPNext site."), frappe.PermissionError)
	flag = str(enabled) not in {"0", "false", "False"}
	return set_site_enabled_record(site, flag)


def _connected_site(site: str):
	_manager()
	from nudg.integrations.erpnext.service import _load_site

	doc = _load_site(site)
	if doc is None:
		frappe.throw(_("Connect the ERPNext site first."))
	allowed = _allowed_accounts()
	if allowed is not None and doc.whatsapp_account not in allowed:
		frappe.throw(_("You cannot change that ERPNext site."), frappe.PermissionError)
	return doc


@frappe.whitelist()
def list_remote_doctypes(site: str, query: str | None = None) -> list[dict]:
	_connected_site(site)
	return list_doctypes(site, query)


@frappe.whitelist()
def describe_remote_doctype(site: str, doctype: str) -> dict:
	_connected_site(site)
	try:
		return describe_doctype(site, doctype)
	except PayloadError as exc:
		frappe.throw(str(exc))


@frappe.whitelist()
def list_alert_templates(site: str) -> list[dict]:
	_connected_site(site)
	return list_templates(site)


@frappe.whitelist()
def list_alerts(site: str) -> list[dict]:
	_connected_site(site)
	return list_alert_records(site)


@frappe.whitelist()
def create_alert(
	site: str,
	doctype: str,
	event: str,
	phone_field: str,
	template: str,
	variable_map: dict | str | None = None,
) -> dict:
	_connected_site(site)
	return create_alert_record(site, doctype, event, phone_field, template, variable_map)


@frappe.whitelist()
def set_alert_enabled(site: str, alert: str, enabled: int | str = 1) -> dict:
	_connected_site(site)
	flag = str(enabled) not in {"0", "false", "False"}
	return set_alert_enabled_record(site, alert, flag)


@frappe.whitelist()
def delete_alert(site: str, alert: str) -> dict:
	_connected_site(site)
	return delete_alert_record(site, alert)
