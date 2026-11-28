# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Connect an ERPNext site. Document rules stay on that site's Notification.

Nudge receives WhatsApp webhooks and document send requests. When the account
is connected, chats are stored on that site. This site still sends through Meta.
"""

from __future__ import annotations

import json
import secrets

import frappe
from frappe import _

from nudg.integrations.erpnext.client import ERPNextClient, ERPNextClientError
from nudg.integrations.erpnext.deliver import DeliveryError, deliver_template
from nudg.integrations.erpnext.payload import (
	MAX_BODY_BYTES,
	PayloadError,
	assert_plain_label,
	payload_fingerprint,
	phone_from_event,
	recipient_is_usable,
	signatures_match,
	token_matches,
)
from nudg.integrations.erpnext.safety import SiteURLError, validate_site_url
from nudg.services.consent import is_contact_opted_out
from nudg.utils.phone import find_matching_profile

_UNKNOWN_SECRET = "nudge-unknown-erpnext-site"
_SEEN_TTL = 7 * 24 * 3600
_RATE_LIMIT = 120


def prepare_site_oauth(
	site_name: str,
	site_url: str,
	whatsapp_account: str | None = None,
	client_id: str | None = None,
	client_secret: str | None = None,
) -> dict:
	"""Create or update a per-account Connected App for OAuth 2.0 and return its Redirect URI."""
	site_name = assert_plain_label(site_name, "Site name")
	try:
		canonical = validate_site_url(site_url, allow_http=_allow_http(), allow_loopback=_allow_http())
	except SiteURLError as exc:
		frappe.throw(str(exc))

	if not whatsapp_account or not frappe.db.exists("WA Account", whatsapp_account):
		# Look for existing WA Account bound to this site_name
		existing = frappe.db.get_value("WA Account", {"erp_site_name": site_name}, "name")
		if existing:
			whatsapp_account = existing
		else:
			# Auto-create a pending container WA Account for this site so users without accounts can connect
			placeholder_name = site_name
			if frappe.db.exists("WA Account", placeholder_name):
				placeholder_name = f"{site_name} (Site)"
			doc = frappe.get_doc({
				"doctype": "WA Account",
				"account_name": placeholder_name,
				"status": "Inactive",
				"erp_site_name": site_name,
				"erp_site_url": canonical,
				"erp_status": "Pending",
			})
			doc.insert(ignore_permissions=True)
			from nudg.security import ensure_account_user_permission

			ensure_account_user_permission(doc.name, frappe.session.user)
			whatsapp_account = doc.name

	doc = frappe.get_doc("WA Account", whatsapp_account)
	other = frappe.db.get_value(
		"WA Account",
		{"erp_site_name": site_name, "name": ["!=", whatsapp_account]},
		"name",
	)
	if other:
		frappe.throw(_("Site name {0} is already connected on {1}.").format(site_name, other))

	app = _upsert_connected_app(
		existing_name=doc.get("erp_connected_app"),
		site_name=site_name,
		site_url=canonical,
		whatsapp_account=whatsapp_account,
		client_id=client_id,
		client_secret=client_secret,
	)
	_sync_connected_app_permissions(app.name, whatsapp_account)

	if not doc.get("erp_inbound_secret"):
		doc.erp_inbound_secret = secrets.token_urlsafe(32)
	url_changed = (doc.get("erp_site_url") or "") != canonical
	doc.erp_site_name = site_name
	doc.erp_site_url = canonical
	doc.erp_connected_app = app.name
	if frappe.session.user not in (None, "Guest"):
		doc.erp_oauth_user = frappe.session.user
	if not doc.erp_status or doc.erp_status == "Disconnected":
		doc.erp_status = "Pending"
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	public = _public_site(doc)
	public["redirect_uri"] = app.redirect_uri or ""
	return public


def authorize_site(site_name: str, success_uri: str | None = None) -> dict:
	view = _load_site(site_name)
	if not view or not getattr(view, "connected_app", None):
		frappe.throw(_("Prepare site OAuth first."))
	app = frappe.get_doc("Connected App", view.connected_app)
	oauth_user = frappe.session.user
	if oauth_user in (None, "Guest"):
		frappe.throw(_("Log in to authorize."), frappe.PermissionError)
	frappe.db.set_value("WA Account", view.account, "erp_oauth_user", oauth_user, update_modified=False)
	target = success_uri or "/app/nudg"
	authorization_url = app.initiate_web_application_flow(user=oauth_user, success_uri=target)
	return {
		"authorization_url": authorization_url,
		"redirect_uri": app.redirect_uri or "",
	}


def verify_site(site_name: str) -> dict:
	from nudg.integrations.erpnext.verify import verify_remote_site
	view = _load_site(site_name)
	if not view:
		frappe.throw(_("External site not found."))
	client = _client_for_site(view)
	if not client:
		_mark_oauth_error(view.account, "Could not initialize client for external site.")
		return {"ok": False, "status": "Error", "checks": []}
	outcome = verify_remote_site(client)
	doc = frappe.get_doc("WA Account", view.account)
	doc.erp_status = outcome.get("status") or "Error"
	doc.erp_remote_user = outcome.get("remote_user") or ""
	doc.erp_last_error = outcome.get("detail") or ""
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	_announce_site_check(outcome)
	return outcome


def disconnect_site(site_name: str) -> dict:
	view = _load_site(site_name)
	if not view:
		frappe.throw(_("External site not found."))
	doc = frappe.get_doc("WA Account", view.account)
	doc.erp_status = "Disconnected"
	doc.erp_last_error = ""
	connected_app = getattr(doc, "erp_connected_app", None)
	doc.erp_connected_app = None
	doc.erp_oauth_user = None
	doc.save(ignore_permissions=True)
	if connected_app and frappe.db.exists("Connected App", connected_app):
		frappe.delete_doc("Connected App", connected_app, ignore_permissions=True)
	frappe.db.commit()
	return _public_site(doc)


def get_remote_wa_accounts(site_name: str) -> list[dict]:
	"""Fetch the list of WA Accounts available on the connected external site."""
	view = _load_site(site_name)
	if not view:
		frappe.throw(_("External site not found."))
	client = _client_for_site(view)
	if not client:
		frappe.throw(_("Could not initialize external site client. Make sure the site is authorized and verified."))

	remote_accounts = []
	try:
		res = client.request("GET", "/api/method/nudg.desk_api.list_user_accounts")
		if isinstance(res, dict) and isinstance(res.get("message"), list):
			remote_accounts = res["message"]
	except Exception:
		pass

	if not remote_accounts:
		try:
			remote_accounts = client.get_resources(
				"WA Account",
				fields=["name", "account_name", "status", "phone_id", "business_id", "app_id", "auto_read_receipts", "is_default"],
				limit=50,
			)
		except Exception:
			pass

	results = []
	for acc in remote_accounts:
		acc_name = acc.get("account_name") or acc.get("name") or ""
		phone_id = str(acc.get("phone_id") or "").strip()
		business_id = str(acc.get("business_id") or "").strip()
		app_id = str(acc.get("app_id") or "").strip()
		status = acc.get("status") or "Active"

		exists = bool(
			frappe.db.exists("WA Account", acc_name)
			or (phone_id and frappe.db.exists("WA Account", {"phone_id": phone_id}))
		)
		local_matched = ""
		if frappe.db.exists("WA Account", acc_name):
			local_matched = acc_name
		elif phone_id and frappe.db.exists("WA Account", {"phone_id": phone_id}):
			local_matched = frappe.db.get_value("WA Account", {"phone_id": phone_id}, "name")

		results.append({
			"name": acc.get("name") or acc_name,
			"account_name": acc_name,
			"phone_id": phone_id,
			"business_id": business_id,
			"app_id": app_id,
			"status": status,
			"auto_read_receipts": acc.get("auto_read_receipts", 0),
			"is_default": acc.get("is_default", 0),
			"exists_locally": exists,
			"local_account": local_matched,
		})
	return results


def pull_remote_wa_accounts(site_name: str, selected_accounts: list) -> dict:
	"""Pull and create or update local WA Accounts from the connected external site."""
	view = _load_site(site_name)
	if not view:
		frappe.throw(_("External site not found."))

	from nudg.security import ensure_account_user_permission

	created = 0
	updated = 0
	pulled_accounts = []

	for acc_data in selected_accounts:
		if isinstance(acc_data, str):
			acc_name = acc_data.strip()
			acc_data = {"account_name": acc_name}
		else:
			acc_name = (acc_data.get("account_name") or acc_data.get("name") or "").strip()

		if not acc_name:
			continue

		phone_id = str(acc_data.get("phone_id") or "").strip()
		business_id = str(acc_data.get("business_id") or "").strip()
		app_id = str(acc_data.get("app_id") or "").strip()
		status = acc_data.get("status") or "Active"
		auto_read = 1 if acc_data.get("auto_read_receipts") else 0

		# Check if local account exists
		local_name = None
		if frappe.db.exists("WA Account", acc_name):
			local_name = acc_name
		elif phone_id and frappe.db.exists("WA Account", {"phone_id": phone_id}):
			local_name = frappe.db.get_value("WA Account", {"phone_id": phone_id}, "name")
		elif view.account and frappe.db.exists("WA Account", view.account):
			holder = frappe.get_doc("WA Account", view.account)
			if not holder.phone_id:
				local_name = holder.name

		if local_name:
			doc = frappe.get_doc("WA Account", local_name)
			# If the existing account was just the placeholder named after the site, rename it
			if (doc.name == view.name or doc.name == f"{view.name} (Site)") and not frappe.db.exists("WA Account", acc_name):
				frappe.rename_doc("WA Account", doc.name, acc_name, force=True)
				doc = frappe.get_doc("WA Account", acc_name)

			if phone_id:
				doc.phone_id = phone_id
			if business_id:
				doc.business_id = business_id
			if app_id:
				doc.app_id = app_id
			doc.status = status
			doc.auto_read_receipts = auto_read
			doc.erp_site_name = view.name
			doc.erp_site_url = view.site_url
			doc.erp_connected_app = view.connected_app
			doc.erp_status = "Connected"
			if frappe.session.user not in (None, "Guest"):
				doc.erp_oauth_user = frappe.session.user
			doc.save(ignore_permissions=True)
			ensure_account_user_permission(doc.name, frappe.session.user)
			updated += 1
			pulled_accounts.append(doc.name)
		else:
			new_doc = frappe.get_doc({
				"doctype": "WA Account",
				"account_name": acc_name,
				"phone_id": phone_id,
				"business_id": business_id,
				"app_id": app_id,
				"status": status,
				"auto_read_receipts": auto_read,
				"erp_site_name": view.name,
				"erp_site_url": view.site_url,
				"erp_connected_app": view.connected_app,
				"erp_status": "Connected",
				"erp_oauth_user": frappe.session.user if frappe.session.user not in (None, "Guest") else "",
			})
			new_doc.insert(ignore_permissions=True)
			ensure_account_user_permission(new_doc.name, frappe.session.user)
			created += 1
			pulled_accounts.append(new_doc.name)

	frappe.db.commit()
	return {
		"ok": True,
		"created": created,
		"updated": updated,
		"accounts": pulled_accounts,
	}


def push_wa_account_to_remote(account_name: str, site_name: str) -> dict:
	"""Push local WA Account details (phone_id, business_id, app_id, status) to the connected remote site."""
	if not frappe.db.exists("WA Account", account_name):
		frappe.throw(_("Local WhatsApp Account not found."))
	view = _load_site(site_name)
	if not view:
		frappe.throw(_("External site not found."))
	client = _client_for_site(view)
	if not client:
		frappe.throw(_("Could not initialize external site client."))

	doc = frappe.get_doc("WA Account", account_name)
	payload = {
		"name": doc.account_name or doc.name,
		"phone_id": doc.phone_id or "",
		"business_id": doc.business_id or "",
		"app_id": doc.app_id or "",
		"status": doc.status or "Active",
		"auto_read_receipts": doc.auto_read_receipts or 0,
	}
	try:
		client.request("POST", "/api/method/nudg.desk_api.update_whatsapp_account", json=payload)
		return {"ok": True, "detail": "Account updated on remote site."}
	except Exception:
		try:
			client.request("PUT", f"/api/resource/WA%20Account/{doc.account_name or doc.name}", json=payload)
			return {"ok": True, "detail": "Account updated on remote site via resource API."}
		except Exception as exc:
			frappe.throw(_("Failed to push account to remote site: {0}").format(str(exc)))


def connect_site(
	site_name: str,
	site_url: str,
	api_key: str,
	api_secret: str,
	whatsapp_account: str,
) -> dict:
	site_name = assert_plain_label(site_name, "Site name")
	if not whatsapp_account or not frappe.db.exists("WA Account", whatsapp_account):
		frappe.throw(_("Choose a WhatsApp account that is already connected in Nudge."))
	try:
		canonical = validate_site_url(site_url, allow_http=_allow_http(), allow_loopback=_allow_http())
	except SiteURLError as exc:
		frappe.throw(str(exc))
	doc = frappe.get_doc("WA Account", whatsapp_account)
	other = frappe.db.get_value(
		"WA Account",
		{"erp_site_name": site_name, "name": ["!=", whatsapp_account]},
		"name",
	)
	if other:
		frappe.throw(_("Site name {0} is already connected on {1}.").format(site_name, other))
	if not doc.get("erp_inbound_secret"):
		doc.erp_inbound_secret = secrets.token_urlsafe(32)
	doc.erp_site_name = site_name
	doc.erp_site_url = canonical
	doc.erp_api_key = api_key.strip()
	doc.erp_api_secret = api_secret
	# Saving runs the site check and sets Connected or Error.
	frappe.flags.nudg_skip_site_popup = True
	try:
		doc.save(ignore_permissions=True)
	finally:
		frappe.flags.nudg_skip_site_popup = False
	public = _public_site(_site_view(doc))
	check = getattr(doc.flags, "nudg_site_check", None) or {}
	public["ok"] = bool(check.get("ok"))
	public["reason"] = check.get("reason") or ""
	public["checks"] = list(check.get("checks") or [])
	return public


def set_site_enabled(site: str, enabled: bool) -> dict:
	view = _require_site(site)
	doc = frappe.get_doc("WA Account", view.account)
	doc.erp_status = "Connected" if enabled else "Disabled"
	doc.save(ignore_permissions=True)
	return _public_site(_site_view(doc))


def accept_event(raw: bytes, site_header: str | None, signature: str | None, bearer: str | None) -> dict:
	"""Send one template requested by an ERPNext Notification. HTTP 200 unless auth fails."""
	if raw is None:
		raw = b""
	if len(raw) > MAX_BODY_BYTES:
		frappe.throw(_("The ERPNext payload is too large."), frappe.ValidationError)

	site_name = (site_header or "").strip()
	site = _load_site(site_name) if site_name else None
	secret = _UNKNOWN_SECRET
	if site:
		try:
			secret = site.get_password("inbound_secret") or _UNKNOWN_SECRET
		except Exception:
			secret = _UNKNOWN_SECRET
	authorized = signatures_match(secret, raw, signature) if signature else token_matches(secret, bearer)
	if site is None or not authorized:
		frappe.throw(_("The ERPNext event could not be authenticated."), frappe.AuthenticationError)

	try:
		body = json.loads(raw.decode("utf-8"))
	except (UnicodeDecodeError, json.JSONDecodeError):
		frappe.throw(_("The ERPNext payload must be JSON."), frappe.ValidationError)
	if not isinstance(body, dict):
		frappe.throw(_("The ERPNext payload must be a JSON object."), frappe.ValidationError)
	if body.get("site") and str(body.get("site")) != site.name:
		frappe.throw(_("The ERPNext event is for a different site."), frappe.AuthenticationError)
	if site.status != "Connected":
		return {"ok": True, "status": "Ignored", "detail": "The ERPNext connection is disabled."}

	template = str(body.get("template") or "").strip()
	remote_doctype = str(body.get("doctype") or "").strip()
	remote_name = str(body.get("name") or "").strip()
	if not template or not remote_doctype or not remote_name:
		return {"ok": True, "status": "Ignored", "detail": "Template, document type, and document name are required."}

	phone = phone_from_event(body, None)
	if not recipient_is_usable(phone):
		return {"ok": True, "status": "Skipped", "detail": "The document has no usable mobile number."}
	if _opted_out(phone, site.whatsapp_account):
		return {"ok": True, "status": "Skipped", "detail": "The customer has opted out of WhatsApp."}

	fingerprint = payload_fingerprint(body)
	if not _remember(site.name, fingerprint):
		return {"ok": True, "status": "Duplicate"}
	if not _under_rate_limit(site.name):
		_forget(site.name, fingerprint)
		frappe.local.response["http_status_code"] = 429
		frappe.throw(_("This ERPNext site is sending events too quickly."), frappe.ValidationError)

	variables = body.get("variables") if isinstance(body.get("variables"), dict) else {}
	parameters = {str(key): "" if value is None else str(value) for key, value in variables.items()}
	preview = f"Template {template} for {remote_doctype} {remote_name}"
	previous = getattr(frappe.session, "user", None)
	if previous in (None, "Guest"):
		frappe.set_user("Administrator")
	try:
		sent = deliver_template(
			account=site.whatsapp_account,
			template=template,
			recipient=phone,
			body_parameters=parameters,
			preview=preview,
		)
	except DeliveryError as exc:
		if exc.kind == "retryable" and not exc.message_id:
			_forget(site.name, fingerprint)
		_note(site, str(exc))
		return {"ok": False, "status": "Failed", "detail": str(exc)[:300]}
	finally:
		if previous:
			frappe.set_user(previous)

	_note_sent(site)
	_writeback_once(site, remote_doctype, remote_name, template, phone, sent["message_id"])
	return {"ok": True, "status": "Sent", "message_id": sent["message_id"]}


def _writeback_once(site, remote_doctype: str, remote_name: str, template: str, phone: str, message_id: str) -> None:
	"""Tell the client site a template was sent. A down site does not hold the WhatsApp message back."""
	from nudg.integrations.site_sync import call_with_retry, is_site_down, mark_site_unreachable

	client = _client_for_site(site)
	if client is None:
		mark_site_unreachable(site.account, "Could not sign in to the ERPNext site.")
		return

	def send():
		client.create_communication(
			reference_doctype=remote_doctype,
			reference_name=remote_name,
			subject=f"WhatsApp sent for {remote_name}"[:140],
			content=f"Nudge sent template {template} to {phone}. Message {message_id}."[:1000],
			phone=phone,
		)

	try:
		_, error = call_with_retry(send)
	except SiteURLError as exc:
		mark_site_unreachable(site.account, str(exc))
		return
	if error is not None and is_site_down(error):
		mark_site_unreachable(site.account, str(error))


def _remember(site: str, fingerprint: str) -> bool:
	"""Return False when this exact send was already accepted. No DocType is stored."""
	cache = frappe.cache()
	key = f"nudg:erpnext:sent:{site}:{fingerprint}"
	if cache.get_value(key):
		return False
	cache.set_value(key, "1", expires_in_sec=_SEEN_TTL)
	return True


def _forget(site: str, fingerprint: str) -> None:
	frappe.cache().delete_value(f"nudg:erpnext:sent:{site}:{fingerprint}")


def _under_rate_limit(site: str) -> bool:
	from frappe.utils import now_datetime

	cache = frappe.cache()
	key = f"nudg:erpnext:rate:{site}:{now_datetime().strftime('%Y%m%d%H%M')}"
	current = int(cache.get_value(key) or 0)
	if current >= _RATE_LIMIT:
		return False
	cache.set_value(key, current + 1, expires_in_sec=120)
	return True


def _opted_out(recipient: str, account: str) -> bool:
	profile = find_matching_profile(recipient, account)
	return bool(profile and is_contact_opted_out(profile))


def _note(site, message: str) -> None:
	frappe.db.set_value("WA Account", site.account, "erp_last_error", message[:300], update_modified=False)


def _note_sent(site) -> None:
	frappe.db.set_value("WA Account", site.account, "erp_last_error", "", update_modified=False)


def _oauth_client_for_site(site) -> ERPNextClient | None:
	if not getattr(site, "connected_app", None) or not frappe.db.exists("Connected App", site.connected_app):
		return None
	app = frappe.get_doc("Connected App", site.connected_app)
	oauth_user = getattr(site, "oauth_user", None) or frappe.session.user
	if not oauth_user or oauth_user == "Guest":
		oauth_user = getattr(site, "remote_user", None)
	token_cache = app.get_active_token(user=oauth_user) if oauth_user else None
	if not token_cache:
		_mark_oauth_error(site.account, "OAuth token expired or not authorized.")
		return None
	return ERPNextClient(site.site_url, oauth_session=app.get_oauth2_session(user=oauth_user), allow_http=_allow_http(), allow_loopback=_allow_http())


def _mark_oauth_error(account: str, reason: str) -> None:
	frappe.db.set_value(
		"WA Account",
		account,
		{"erp_status": "Error", "erp_last_error": reason},
		update_modified=False,
	)


def _client_for_site(site) -> ERPNextClient | None:
	if getattr(site, "connected_app", None):
		return _oauth_client_for_site(site)
	try:
		return _client(site.site_url, site.get_password("api_key"), site.get_password("api_secret"))
	except Exception:
		return None


def _client(site_url: str, api_key: str, api_secret: str) -> ERPNextClient:
	return ERPNextClient(site_url, api_key, api_secret, allow_http=_allow_http(), allow_loopback=_allow_http())


def _require_site(name: str):
	site = _load_site(name)
	if site is None:
		frappe.throw(_("Connect the ERPNext site first."))
	return site


def _load_site(name: str):
	"""Find the connection stored on a WA Account by account name or site name."""
	name = (name or "").strip()
	if not name or not frappe.db.exists("DocType", "WA Account"):
		return None
	if not frappe.db.has_column("WA Account", "erp_site_name"):
		return None
	account_name = None
	if frappe.db.exists("WA Account", name):
		site_name = frappe.db.get_value("WA Account", name, "erp_site_name")
		if site_name:
			account_name = name
	if not account_name:
		account_name = frappe.db.get_value("WA Account", {"erp_site_name": name}, "name")
	if not account_name:
		return None
	return _site_view(frappe.get_doc("WA Account", account_name))


def validate_account_site(doc, method=None):
	"""Check the Connected Site tab when a WhatsApp account is saved."""
	url = (doc.get("erp_site_url") or "").strip()
	site_name = (doc.get("erp_site_name") or "").strip()
	if not url and not site_name:
		return
	if url:
		try:
			doc.erp_site_url = validate_site_url(url, allow_http=_allow_http(), allow_loopback=_allow_http())
		except SiteURLError as exc:
			frappe.throw(_(str(exc)))
	if site_name and doc.name:
		other = frappe.db.get_value(
			"WA Account",
			{"erp_site_name": site_name, "name": ["!=", doc.name]},
			"name",
		)
		if other:
			frappe.throw(_("Site name {0} is already connected on {1}.").format(site_name, other))
	if not doc.get("erp_inbound_secret"):
		doc.erp_inbound_secret = secrets.token_urlsafe(32)
	if not doc.get("erp_status"):
		doc.erp_status = "Pending"
	if not _should_check_site(doc):
		return
	key = _password(doc, "erp_api_key")
	secret = _password(doc, "erp_api_secret")
	if not key or not secret:
		reason = "An API key and API secret are required."
		doc.erp_status = "Pending"
		doc.erp_last_error = reason
		_announce_site_check(
			{
				"ok": False,
				"status": "Pending",
				"remote_user": "",
				"reason": reason,
				"checks": [{"name": "API credentials", "ok": False, "detail": reason}],
			}
		)
		return
	outcome = _check_saved_site(doc, key, secret)
	doc.flags.nudg_site_check = outcome
	doc.erp_status = outcome["status"]
	if outcome.get("remote_user"):
		doc.erp_remote_user = outcome["remote_user"]
	doc.erp_last_error = (outcome.get("reason") or "")[:1000]
	_announce_site_check(outcome)
	if outcome.get("ok") and doc.name:
		_flush_after_save(doc.name)


class _SiteView:
	"""Read a connected site from the fields stored on its WA Account."""

	def __init__(self, account):
		self.account = account.name
		self.name = account.get("erp_site_name") or account.name
		self.site_url = account.get("erp_site_url")
		self.status = account.get("erp_status") or "Pending"
		self.whatsapp_account = account.name
		self.remote_user = account.get("erp_remote_user")
		self.last_error = account.get("erp_last_error")
		self.connected_app = account.get("erp_connected_app") or ""
		self.oauth_user = account.get("erp_oauth_user") or ""
		self._account = account

	def get_password(self, field: str) -> str:
		mapped = {
			"api_key": "erp_api_key",
			"api_secret": "erp_api_secret",
			"inbound_secret": "erp_inbound_secret",
		}
		return self._account.get_password(mapped[field])


def _site_view(account) -> _SiteView:
	return _SiteView(account)


def _allow_http() -> bool:
	return bool(getattr(frappe.conf, "developer_mode", False))


def _should_check_site(doc) -> bool:
	"""Run the remote check when credentials are saved, or while the site is not healthy."""
	if frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch or frappe.flags.in_import:
		return False
	if frappe.flags.in_test and not frappe.flags.get("nudg_verify_remote_site"):
		return False
	if not (doc.get("erp_site_url") or "").strip():
		return False
	changed = _site_fields_changed(doc)
	status = doc.get("erp_status") or "Pending"
	if status == "Disabled" and not changed:
		return False
	if status == "Connected" and not changed and not doc.has_value_changed("erp_status"):
		return False
	return True


def _site_fields_changed(doc) -> bool:
	return any(
		doc.has_value_changed(field)
		for field in ("erp_site_url", "erp_site_name", "erp_api_key", "erp_api_secret")
	)


def _password(doc, field: str) -> str:
	if not doc.get(field):
		return ""
	try:
		return doc.get_password(field) or ""
	except Exception:
		return str(doc.get(field) or "")


def _check_saved_site(doc, api_key: str, api_secret: str) -> dict:
	from nudg.integrations.erpnext.verify import verify_remote_site

	try:
		client = _client(doc.erp_site_url, api_key, api_secret)
		return verify_remote_site(client)
	except (ERPNextClientError, SiteURLError) as exc:
		reason = str(exc)[:1000]
		return {
			"ok": False,
			"status": "Error",
			"remote_user": "",
			"reason": reason,
			"checks": [{"name": "Sign in", "ok": False, "detail": reason}],
		}
	except Exception:
		frappe.log_error(title="Nudg site verification")
		reason = "The site check could not be finished. Save again after the site is reachable."
		return {
			"ok": False,
			"status": "Error",
			"remote_user": "",
			"reason": reason,
			"checks": [{"name": "Sign in", "ok": False, "detail": reason}],
		}


def _announce_site_check(outcome: dict) -> None:
	if getattr(frappe.flags, "nudg_skip_site_popup", False):
		return
	from frappe.utils import escape_html

	ok = bool(outcome.get("ok"))
	checks = outcome.get("checks") or []
	items = "".join(
		f"<li><b>{escape_html(check.get('name') or '')}.</b> {escape_html(check.get('detail') or '')}</li>"
		for check in checks
	)
	if ok:
		user = escape_html(outcome.get("remote_user") or "")
		lead = _(
			"Everything is fine. Signed in as {0}. WhatsApp is installed on that site and this user has the permissions Nudg needs. Site status is Connected."
		).format(user)
	else:
		lead = _("The site was not connected. Fix these, then save again.")
	message = f"<p>{lead}</p><ul>{items}</ul>"
	frappe.msgprint(
		message,
		title=_("Site verified") if ok else _("Could not verify the ERPNext site"),
		indicator="green" if ok else "red",
	)


def _flush_after_save(account: str) -> None:
	try:
		frappe.enqueue(
			"nudg.integrations.site_sync.flush_account",
			queue="short",
			account=account,
			enqueue_after_commit=True,
		)
	except Exception:
		pass




def _clean_redirect_uri(uri: str | None) -> str:
	if not uri:
		return ""
	import re
	if uri.startswith("https://") and re.search(r":\d+", uri):
		return re.sub(r"(https://[^/:]+):\d+", r"\1", uri)
	return uri


def _upsert_connected_app(
	*,
	existing_name: str | None,
	site_name: str,
	site_url: str,
	whatsapp_account: str,
	client_id: str | None = None,
	client_secret: str | None = None,
):
	if existing_name and frappe.db.exists("Connected App", existing_name):
		app = frappe.get_doc("Connected App", existing_name)
	else:
		app = frappe.new_doc("Connected App")
		app.provider_name = f"External Site - {site_name} ({whatsapp_account})"

	app.authorization_uri = f"{site_url}/api/method/frappe.integrations.oauth2.authorize"
	app.token_uri = f"{site_url}/api/method/frappe.integrations.oauth2.get_token"
	app.revocation_uri = f"{site_url}/api/method/frappe.integrations.oauth2.revoke_token"
	app.userinfo_uri = f"{site_url}/api/method/frappe.integrations.oauth2.openid_profile"
	if not app.get("scopes"):
		app.append("scopes", {"scope": "all"})
	if client_id is not None and client_id.strip():
		app.client_id = client_id.strip()
	if client_secret is not None and client_secret.strip():
		app.client_secret = client_secret.strip()
	app.save(ignore_permissions=True)
	if app.redirect_uri:
		cleaned = _clean_redirect_uri(app.redirect_uri)
		if cleaned != app.redirect_uri:
			app.db_set("redirect_uri", cleaned)
			app.redirect_uri = cleaned
	return app


def _sync_connected_app_permissions(connected_app_name: str, whatsapp_account: str) -> None:
	"""Scope a Connected App to only the users permitted on its WA Account (SaaS tenant isolation)."""
	if not connected_app_name or not frappe.db.exists("DocType", "User Permission"):
		return
	users: set[str] = set()
	if frappe.session.user not in (None, "Guest", "Administrator"):
		users.add(frappe.session.user)
	try:
		permitted = frappe.get_all(
			"User Permission",
			filters={"allow": "WA Account", "for_value": whatsapp_account},
			pluck="user",
		)
		for user in permitted or []:
			if user and user not in ("Guest", "Administrator"):
				users.add(user)
	except Exception:
		pass

	for user in users:
		if not frappe.db.exists(
			"User Permission",
			{"user": user, "allow": "Connected App", "for_value": connected_app_name},
		):
			perm = frappe.new_doc("User Permission")
			perm.user = user
			perm.allow = "Connected App"
			perm.for_value = connected_app_name
			perm.apply_to_all_doctypes = 1
			perm.insert(ignore_permissions=True)


def _public_site(doc) -> dict:
	connected_app = getattr(doc, "erp_connected_app", None) or getattr(doc, "connected_app", "") or ""
	redirect_uri = ""
	client_id = ""
	has_client_credentials = False
	if connected_app and frappe.db.exists("Connected App", connected_app):
		app = frappe.get_doc("Connected App", connected_app)
		redirect_uri = _clean_redirect_uri(app.redirect_uri) or ""
		client_id = app.client_id or ""
		has_client_credentials = bool(app.client_id and _password(app, "client_secret"))
	return {
		"name": doc.account if hasattr(doc, "account") else doc.name,
		"site_name": doc.name if hasattr(doc, "account") else (doc.get("erp_site_name") or doc.name),
		"site_url": doc.site_url if hasattr(doc, "site_url") else doc.get("erp_site_url"),
		"status": doc.status if hasattr(doc, "status") else doc.get("erp_status"),
		"whatsapp_account": doc.whatsapp_account if hasattr(doc, "whatsapp_account") else doc.name,
		"remote_user": doc.remote_user if hasattr(doc, "remote_user") else doc.get("erp_remote_user"),
		"last_error": doc.last_error if hasattr(doc, "last_error") else doc.get("erp_last_error"),
		"connected_app": connected_app,
		"client_id": client_id,
		"oauth_user": getattr(doc, "oauth_user", None) or doc.get("erp_oauth_user") or "",
		"auth_mode": "oauth" if connected_app else "api_key",
		"redirect_uri": redirect_uri,
		"has_client_credentials": has_client_credentials,
	}
