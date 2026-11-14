# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Connect an ERPNext site. Document rules stay on that site's Notification.

Nudge only receives a send request and delivers it with the WhatsApp account
that lives here. Chat and campaigns never wait for the ERPNext site.
"""

from __future__ import annotations

import json

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
		canonical = validate_site_url(site_url, allow_http=_allow_http())
	except SiteURLError as exc:
		frappe.throw(str(exc))
	client = _client(canonical, api_key, api_secret)
	try:
		remote_user = client.get_logged_user()
	except (ERPNextClientError, SiteURLError) as exc:
		frappe.throw(_("Could not sign in to that ERPNext site: {0}").format(exc))

	if frappe.db.exists("ERPNext Site", site_name):
		doc = frappe.get_doc("ERPNext Site", site_name)
	else:
		doc = frappe.new_doc("ERPNext Site")
		doc.site_name = site_name
	doc.site_url = canonical
	doc.api_key = api_key.strip()
	doc.api_secret = api_secret
	doc.whatsapp_account = whatsapp_account
	doc.status = "Connected"
	doc.remote_user = remote_user
	doc.last_error = ""
	doc.save(ignore_permissions=True)
	return _public_site(doc)


def set_site_enabled(site: str, enabled: bool) -> dict:
	doc = _require_site(site)
	doc.status = "Connected" if enabled else "Disabled"
	doc.save(ignore_permissions=True)
	return _public_site(doc)


def accept_event(raw: bytes, site_header: str | None, signature: str | None, bearer: str | None) -> dict:
	"""Send one template requested by an ERPNext Notification. HTTP 200 unless auth fails."""
	if raw is None:
		raw = b""
	if len(raw) > MAX_BODY_BYTES:
		frappe.throw(_("The ERPNext payload is too large."), frappe.ValidationError)

	site_name = (site_header or "").strip()
	site = frappe.get_doc("ERPNext Site", site_name) if site_name and frappe.db.exists("ERPNext Site", site_name) else None
	secret = site.get_password("inbound_secret") if site else _UNKNOWN_SECRET
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
	"""One attempt. A down ERPNext site does not hold the WhatsApp message back."""
	try:
		_client_for_site(site).create_communication(
			reference_doctype=remote_doctype,
			reference_name=remote_name,
			subject=f"WhatsApp sent for {remote_name}"[:140],
			content=f"Nudge sent template {template} to {phone}. Message {message_id}."[:1000],
			phone=phone,
		)
	except (ERPNextClientError, SiteURLError):
		return


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
	frappe.db.set_value("ERPNext Site", site.name, "last_error", message[:300], update_modified=False)


def _note_sent(site) -> None:
	frappe.db.set_value("ERPNext Site", site.name, "last_error", "", update_modified=False)


def _client_for_site(site) -> ERPNextClient:
	return _client(site.site_url, site.get_password("api_key"), site.get_password("api_secret"))


def _client(site_url: str, api_key: str, api_secret: str) -> ERPNextClient:
	return ERPNextClient(site_url, api_key, api_secret, allow_http=_allow_http())


def _require_site(name: str):
	if not name or not frappe.db.exists("ERPNext Site", name):
		frappe.throw(_("Connect the ERPNext site first."))
	return frappe.get_doc("ERPNext Site", name)


def _allow_http() -> bool:
	return bool(getattr(frappe.conf, "developer_mode", False))


def _public_site(doc) -> dict:
	return {
		"name": doc.name,
		"site_url": doc.site_url,
		"status": doc.status,
		"whatsapp_account": doc.whatsapp_account,
		"remote_user": doc.remote_user,
		"last_error": doc.last_error,
	}
