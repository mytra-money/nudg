# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Embedded Signup v4: exchange the popup code and store the customer token."""

from __future__ import annotations

import re
import secrets
from typing import Any

import requests

import frappe
from frappe import _

GRAPH_DEFAULT = "v23.0"
SETTINGS_DOCTYPE = "WA Signup Settings"
LEGACY_SETTINGS_DOCTYPE = "WhatsApp Signup Settings"
_TOKEN_RE = re.compile(r"EAA[A-Za-z0-9]+")
_CODE_RE = re.compile(r"(code=)[^&\s]+", re.IGNORECASE)
_ACCESS_RE = re.compile(r"(access_token=)[^&\s]+", re.IGNORECASE)
_PERMISSION_MARKERS = (
	"missing permission",
	"does not exist",
	"unsupported post",
	"does not support this operation",
)


class EmbeddedSignupError(frappe.ValidationError):
	def __init__(self, message: str, detail: str | None = None):
		super().__init__(message)
		self.detail = detail or message


def redact(text: str | None) -> str:
	if not text:
		return ""
	cleaned = _TOKEN_RE.sub("EAA[REDACTED]", str(text))
	cleaned = _CODE_RE.sub(r"\1[REDACTED]", cleaned)
	return _ACCESS_RE.sub(r"\1[REDACTED]", cleaned)


def user_message(detail: str | None) -> str:
	"""Short text safe to show in the desk. The Graph sentence stays in the log."""
	text = (detail or "").lower()
	if "already registered" in text or "already verified" in text:
		return _("This number is already registered.")
	if any(marker in text for marker in _PERMISSION_MARKERS):
		return _("WhatsApp could not finish setup. A Meta app admin needs to grant WhatsApp permissions, then connect again.")
	if "could not reach" in text or "timed out" in text or "timeout" in text:
		return _("Could not reach WhatsApp. Check the connection and try again.")
	return _("WhatsApp could not finish setup. Try connecting again.")


def make_pin() -> str:
	return f"{secrets.randbelow(1_000_000):06d}"


def public_config() -> dict[str, Any]:
	"""Values the browser may see. The app secret stays on the server."""
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return {
			"enabled": False,
			"ready": False,
			"app_id": "752752485429112",
			"config_id": "",
			"graph_api_version": GRAPH_DEFAULT,
			"has_secret": False,
			"missing": ["enabled", "app_id", "config_id", "app_secret"],
		}
	doc = frappe.get_single(SETTINGS_DOCTYPE)
	app_id = (doc.app_id or "").strip()
	config_id = (doc.config_id or "").strip()
	version = (doc.graph_api_version or GRAPH_DEFAULT).strip() or GRAPH_DEFAULT
	has_secret = bool(_read_secret(doc))
	missing = []
	if not doc.enabled:
		missing.append("enabled")
	if not app_id:
		missing.append("app_id")
	if not config_id:
		missing.append("config_id")
	if not has_secret:
		missing.append("app_secret")
	return {
		"enabled": bool(doc.enabled),
		"ready": not missing,
		"app_id": app_id or "752752485429112",
		"config_id": config_id,
		"graph_api_version": version,
		"has_secret": has_secret,
		"missing": missing,
	}


def save_settings(app_id: str, config_id: str, app_secret: str | None = None, graph_api_version: str | None = None) -> dict[str, Any]:
	app_id = (app_id or "").strip()
	config_id = (config_id or "").strip()
	version = (graph_api_version or GRAPH_DEFAULT).strip() or GRAPH_DEFAULT
	if not app_id.isdigit():
		frappe.throw(_("Enter the numeric Meta App ID."))
	if not config_id.isdigit():
		frappe.throw(_("Enter the numeric Embedded Signup configuration ID."))
	if not version.startswith("v"):
		frappe.throw(_("Graph API version should look like v23.0."))

	doc = frappe.get_single(SETTINGS_DOCTYPE)
	doc.enabled = 1
	doc.app_id = app_id
	doc.config_id = config_id
	doc.graph_api_version = version
	secret = (app_secret or "").strip()
	if secret:
		doc.app_secret = secret
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return public_config()


def complete_signup(
	code: str,
	waba_id: str | None = None,
	phone_number_id: str | None = None,
	account_name: str | None = None,
) -> dict[str, Any]:
	code = (code or "").strip()
	waba_id = (waba_id or "").strip()
	phone_number_id = (phone_number_id or "").strip()
	account_name = (account_name or "").strip()
	if not code:
		frappe.throw(_("Embedded Signup did not return a code."))

	settings = _require_settings()
	token = exchange_code(settings["app_id"], settings["app_secret"], code, settings["graph_api_version"])
	version = settings["graph_api_version"]
	found: dict[str, Any] = {}
	if not waba_id or not phone_number_id:
		found = _discover_or_empty(token, settings["app_id"], settings["app_secret"], version)
		waba_id = waba_id or str(found.get("waba_id") or "")
		phone_number_id = phone_number_id or str(found.get("phone_number_id") or "")
	if not waba_id.isdigit() or not phone_number_id.isdigit():
		frappe.throw(_("Embedded Signup did not return a WhatsApp account ID and phone number ID."))

	pin = make_pin()
	subscribed, registered, warnings = _finish_cloud(waba_id, phone_number_id, token, pin, version)
	if warnings:
		if not found:
			found = _discover_or_empty(token, settings["app_id"], settings["app_secret"], version)
		alt_waba, alt_phone = _alternate_ids(waba_id, phone_number_id, found)
		if alt_waba and alt_phone:
			alt_subscribed, alt_registered, alt_warnings = _finish_cloud(alt_waba, alt_phone, token, pin, version)
			if not alt_warnings:
				waba_id, phone_number_id = alt_waba, alt_phone
				subscribed, registered, warnings = alt_subscribed, alt_registered, alt_warnings

	account = _upsert_account(
		account_name=account_name or f"WhatsApp {phone_number_id[-4:]}",
		phone_id=phone_number_id,
		business_id=waba_id,
		access_token=token,
		app_id=settings["app_id"],
		pin=pin if registered else "",
	)
	return {
		"status": "success",
		"account": account,
		"account_name": account_name or f"WhatsApp {phone_number_id[-4:]}",
		"phone_number_id": phone_number_id,
		"waba_id": waba_id,
		"pin": pin if registered else "",
		"ready": bool(subscribed and registered),
		"warnings": warnings,
	}


def exchange_code(app_id: str, app_secret: str, code: str, version: str) -> str:
	response = _graph(
		"GET",
		f"https://graph.facebook.com/{version}/oauth/access_token",
		params={"client_id": app_id, "client_secret": app_secret, "code": code},
	)
	token = str((response or {}).get("access_token") or "").strip()
	if not token:
		raise EmbeddedSignupError(_("Meta did not return a business token."))
	return token


def discover_assets(token: str, app_id: str, app_secret: str, version: str) -> dict[str, Any]:
	app_token = f"{app_id}|{app_secret}"
	debug = _graph(
		"GET",
		f"https://graph.facebook.com/{version}/debug_token",
		params={"input_token": token},
		token=app_token,
	)
	data = (debug or {}).get("data") or {}
	waba_id = ""
	for scope in data.get("granular_scopes") or []:
		if scope.get("scope") in ("whatsapp_business_management", "whatsapp_business_messaging"):
			ids = scope.get("target_ids") or []
			if ids:
				waba_id = str(ids[0])
				break
	phone_number_id = ""
	phone_ids: list[str] = []
	if waba_id:
		numbers = _graph(
			"GET",
			f"https://graph.facebook.com/{version}/{waba_id}/phone_numbers",
			token=token,
		)
		rows = (numbers or {}).get("data") or []
		phone_ids = [str(row.get("id") or "") for row in rows if row.get("id")]
		if phone_ids:
			phone_number_id = phone_ids[0]
	return {"waba_id": waba_id, "phone_number_id": phone_number_id, "phone_number_ids": phone_ids}


def subscribe_app(waba_id: str, token: str, version: str) -> None:
	_graph(
		"POST",
		f"https://graph.facebook.com/{version}/{waba_id}/subscribed_apps",
		token=token,
	)


def register_phone(phone_number_id: str, token: str, pin: str, version: str) -> None:
	try:
		_graph(
			"POST",
			f"https://graph.facebook.com/{version}/{phone_number_id}/register",
			token=token,
			payload={"messaging_product": "whatsapp", "pin": pin},
		)
	except EmbeddedSignupError as exc:
		if _already_registered(exc.detail):
			return
		raise


def _require_settings() -> dict[str, str]:
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		frappe.throw(_("Embedded Signup settings are not installed. Run bench migrate."))
	doc = frappe.get_single(SETTINGS_DOCTYPE)
	app_id = (doc.app_id or "").strip()
	config_id = (doc.config_id or "").strip()
	secret = _read_secret(doc)
	if not doc.enabled or not app_id or not config_id or not secret:
		frappe.throw(_("Save the Meta App ID, configuration ID, and app secret before connecting."))
	return {
		"app_id": app_id,
		"config_id": config_id,
		"app_secret": secret,
		"graph_api_version": (doc.graph_api_version or GRAPH_DEFAULT).strip() or GRAPH_DEFAULT,
	}


def _read_secret(doc) -> str:
	secret = _password_on_doc(doc)
	if secret:
		return secret
	if getattr(doc, "doctype", SETTINGS_DOCTYPE) != SETTINGS_DOCTYPE:
		return ""
	return adopt_legacy_app_secret()


def adopt_legacy_app_secret() -> str:
	"""Move the app secret saved before the DocType rename onto WA Signup Settings.

	Renaming the Single updated ``tabSingles`` and left ``__Auth`` keyed to
	``WhatsApp Signup Settings``. The form still shows a row of dots, and
	``get_password`` on the new Single finds nothing.
	"""
	current = _decrypt_named(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE, "app_secret")
	if current:
		return current
	secret = _decrypt_named(LEGACY_SETTINGS_DOCTYPE, LEGACY_SETTINGS_DOCTYPE, "app_secret")
	if not secret or not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return secret
	try:
		from frappe.utils.password import remove_encrypted_password, set_encrypted_password

		set_encrypted_password(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE, secret, "app_secret")
		remove_encrypted_password(LEGACY_SETTINGS_DOCTYPE, LEGACY_SETTINGS_DOCTYPE, "app_secret")
	except Exception:
		return secret
	return secret


def _password_on_doc(doc) -> str:
	if hasattr(doc, "get_password"):
		try:
			return (doc.get_password("app_secret", raise_exception=False) or "").strip()
		except Exception:
			return ""
	return (getattr(doc, "app_secret", None) or "").strip()


def _decrypt_named(doctype: str, name: str, fieldname: str) -> str:
	from frappe.utils.password import get_decrypted_password

	try:
		value = get_decrypted_password(doctype, name, fieldname, raise_exception=False)
	except Exception:
		return ""
	return (value or "").strip()


def _graph(method: str, url: str, params: dict | None = None, payload: dict | None = None, token: str | None = None) -> dict:
	try:
		return _request_graph(method, url, params, payload, token, query_token=False)
	except EmbeddedSignupError as exc:
		if token and _permission_denied(exc.detail):
			try:
				return _request_graph(method, url, params, payload, token, query_token=True)
			except EmbeddedSignupError as retry_exc:
				_log_meta(retry_exc.detail)
				raise
		_log_meta(exc.detail)
		raise


def _request_graph(
	method: str,
	url: str,
	params: dict | None,
	payload: dict | None,
	token: str | None,
	query_token: bool,
) -> dict:
	query = dict(params or {})
	headers = {}
	if token:
		if query_token:
			query["access_token"] = token
		else:
			headers["Authorization"] = f"Bearer {token}"
	try:
		response = requests.request(method, url, params=query or None, json=payload, headers=headers, timeout=30)
	except requests.RequestException as exc:
		detail = redact(str(exc))
		raise EmbeddedSignupError(user_message(detail), detail) from exc
	try:
		body = response.json()
	except ValueError:
		body = {}
	if response.status_code >= 400 or (isinstance(body, dict) and body.get("error")):
		message = ""
		if isinstance(body, dict) and isinstance(body.get("error"), dict):
			message = body["error"].get("message") or ""
		detail = redact(message or response.text or f"Meta returned HTTP {response.status_code}")
		raise EmbeddedSignupError(user_message(detail), detail)
	return body if isinstance(body, dict) else {}


def _permission_denied(detail: str | None) -> bool:
	text = (detail or "").lower()
	return any(marker in text for marker in _PERMISSION_MARKERS)


def _already_registered(detail: str | None) -> bool:
	text = (detail or "").lower()
	return "already registered" in text or "already verified" in text


def _discover_or_empty(token: str, app_id: str, app_secret: str, version: str) -> dict[str, Any]:
	try:
		return discover_assets(token, app_id, app_secret, version)
	except EmbeddedSignupError as exc:
		_log_meta(exc.detail)
		return {}


def _alternate_ids(waba_id: str, phone_number_id: str, found: dict[str, Any]) -> tuple[str, str]:
	alt_waba = str(found.get("waba_id") or "")
	phones = [str(item) for item in (found.get("phone_number_ids") or []) if item]
	if phone_number_id in phones:
		alt_phone = phone_number_id
	else:
		alt_phone = str(found.get("phone_number_id") or "")
	if not alt_waba.isdigit() or not alt_phone.isdigit():
		return "", ""
	if alt_waba == waba_id and alt_phone == phone_number_id:
		return "", ""
	return alt_waba, alt_phone


def _finish_cloud(waba_id: str, phone_number_id: str, token: str, pin: str, version: str) -> tuple[bool, bool, list[str]]:
	subscribed = False
	registered = False
	warnings: list[str] = []
	try:
		subscribe_app(waba_id, token, version)
		subscribed = True
	except EmbeddedSignupError as exc:
		_log_meta(exc.detail)
		warnings.append(str(exc))
	try:
		register_phone(phone_number_id, token, pin, version)
		registered = True
	except EmbeddedSignupError as exc:
		_log_meta(exc.detail)
		warnings.append(str(exc))
	unique: list[str] = []
	for warning in warnings:
		if warning not in unique:
			unique.append(warning)
	return subscribed, registered, unique


def _log_meta(detail: str) -> None:
	try:
		frappe.log_error(message=redact(detail)[:14000], title="WhatsApp setup")
	except Exception:
		return


def _upsert_account(account_name: str, phone_id: str, business_id: str, access_token: str, app_id: str, pin: str) -> str:
	existing = frappe.db.get_value("WA Account", {"phone_id": phone_id}, "name")
	if existing:
		doc = frappe.get_doc("WA Account", existing)
	else:
		doc = frappe.get_doc({"doctype": "WA Account", "account_name": account_name, "status": "Active"})
	doc.account_name = doc.account_name or account_name
	doc.phone_id = phone_id
	doc.business_id = business_id
	doc.access_token = access_token
	doc.app_id = app_id
	doc.status = "Active"
	if pin and frappe.get_meta("WA Account").get_field("two_step_pin"):
		doc.two_step_pin = pin
	if existing:
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)
	from nudg.security import ensure_account_user_permission

	ensure_account_user_permission(doc.name, frappe.session.user)
	if frappe.db.exists("DocType", "WA Settings"):
		current_default = frappe.db.get_single_value("WA Settings", "default_account")
		if not current_default:
			frappe.db.set_single_value("WA Settings", "default_account", doc.name)
	frappe.db.commit()
	return doc.name
