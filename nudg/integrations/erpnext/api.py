# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Desk API for connecting an ERPNext site. The Notification rule stays on that site."""

from __future__ import annotations

import frappe
from frappe import _

from nudg.integrations.erpnext.payload import PayloadError
from nudg.integrations.erpnext.service import authorize_site as authorize_site_record
from nudg.integrations.erpnext.service import connect_site as connect_site_record
from nudg.integrations.erpnext.service import disconnect_site as disconnect_site_record
from nudg.integrations.erpnext.service import get_remote_wa_accounts as get_remote_wa_accounts_record
from nudg.integrations.erpnext.service import prepare_site_oauth as prepare_site_oauth_record
from nudg.integrations.erpnext.service import pull_remote_wa_accounts as pull_remote_wa_accounts_record
from nudg.integrations.erpnext.service import push_wa_account_to_remote as push_wa_account_to_remote_record
from nudg.integrations.erpnext.service import set_site_enabled as set_site_enabled_record
from nudg.integrations.erpnext.service import verify_site as verify_site_record
from nudg.security import get_user_wa_accounts


def _manager() -> None:
	if frappe.session.user in (None, "Guest"):
		frappe.throw(_("Log in to connect an external site."), frappe.PermissionError)
	roles = set(frappe.get_roles())
	if frappe.session.user != "Administrator" and not roles.intersection({"System Manager", "WhatsApp Manager"}):
		frappe.throw(_("Only a WhatsApp manager can connect an external site."), frappe.PermissionError)


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
	has_oauth_cols = frappe.db.has_column("WA Account", "erp_connected_app")
	fields = [
		"name",
		"erp_site_name",
		"erp_site_url",
		"erp_status",
		"erp_remote_user",
		"erp_last_error",
		"modified",
	]
	if has_oauth_cols:
		fields.extend(["erp_connected_app", "erp_oauth_user"])
	rows = frappe.get_list(
		"WA Account",
		filters={"erp_site_name": ["is", "set"]},
		fields=fields,
		order_by="modified desc",
		limit_page_length=50,
	)
	allowed = _allowed_accounts()
	public = []
	for row in rows:
		if allowed is not None and row.name not in allowed:
			continue
		connected_app = row.get("erp_connected_app") if has_oauth_cols else ""
		redirect_uri = ""
		client_id = ""
		has_client_credentials = False
		if connected_app and frappe.db.exists("Connected App", connected_app):
			from nudg.integrations.erpnext.service import _clean_redirect_uri
			app = frappe.get_doc("Connected App", connected_app)
			redirect_uri = _clean_redirect_uri(app.redirect_uri) or ""
			client_id = app.client_id or ""
			has_client_credentials = bool(app.client_id and app.get("client_secret"))
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
				"connected_app": connected_app or "",
				"client_id": client_id,
				"oauth_user": (row.get("erp_oauth_user") if has_oauth_cols else "") or "",
				"auth_mode": "oauth" if connected_app else "api_key",
				"redirect_uri": redirect_uri,
				"has_client_credentials": has_client_credentials,
			}
		)
	return public


@frappe.whitelist()
def prepare_site_oauth(
	site_name: str,
	site_url: str,
	whatsapp_account: str | None = None,
	client_id: str | None = None,
	client_secret: str | None = None,
) -> dict:
	_manager()
	allowed = _allowed_accounts()
	if allowed is not None and whatsapp_account and whatsapp_account not in allowed:
		frappe.throw(_("You cannot connect an external site to that WhatsApp account."), frappe.PermissionError)
	try:
		return prepare_site_oauth_record(site_name, site_url, whatsapp_account, client_id, client_secret)
	except PayloadError as exc:
		frappe.throw(str(exc))


@frappe.whitelist()
def get_remote_wa_accounts(site: str) -> list[dict]:
	_connected_site(site)
	return get_remote_wa_accounts_record(site)


@frappe.whitelist()
def pull_remote_wa_accounts(site: str, selected_accounts: list | str) -> dict:
	_connected_site(site)
	if isinstance(selected_accounts, str):
		import json
		try:
			selected_accounts = json.loads(selected_accounts)
		except Exception:
			selected_accounts = [selected_accounts]
	return pull_remote_wa_accounts_record(site, selected_accounts or [])


@frappe.whitelist()
def push_wa_account_to_remote(account: str, site: str) -> dict:
	_connected_site(site)
	return push_wa_account_to_remote_record(account, site)


@frappe.whitelist()
def authorize_site(site: str, success_uri: str | None = None) -> dict:
	_connected_site(site)
	return authorize_site_record(site, success_uri)


@frappe.whitelist()
def verify_site(site: str) -> dict:
	_connected_site(site)
	return verify_site_record(site)


@frappe.whitelist()
def disconnect_site(site: str) -> dict:
	_connected_site(site)
	return disconnect_site_record(site)


@frappe.whitelist()
def connect_site(site_name: str, site_url: str, api_key: str, api_secret: str, whatsapp_account: str) -> dict:
	_manager()
	allowed = _allowed_accounts()
	if allowed is not None and whatsapp_account not in allowed:
		frappe.throw(_("You cannot connect an external site to that WhatsApp account."), frappe.PermissionError)
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
		frappe.throw(_("Connect the external site first."))
	allowed = _allowed_accounts()
	if allowed is not None and doc.whatsapp_account not in allowed:
		frappe.throw(_("You cannot change that external site."), frappe.PermissionError)
	flag = str(enabled) not in {"0", "false", "False"}
	return set_site_enabled_record(site, flag)


def _connected_site(site: str):
	_manager()
	from nudg.integrations.erpnext.service import _load_site

	doc = _load_site(site)
	if doc is None:
		frappe.throw(_("Connect the external site first."))
	allowed = _allowed_accounts()
	if allowed is not None and doc.whatsapp_account not in allowed:
		frappe.throw(_("You cannot change that external site."), frappe.PermissionError)
	return doc
