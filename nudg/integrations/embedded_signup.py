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
_TOKEN_RE = re.compile(r"EAA[A-Za-z0-9]+")
_CODE_RE = re.compile(r"(code=)[^&\s]+", re.IGNORECASE)


class EmbeddedSignupError(frappe.ValidationError):
	pass


def redact(text: str | None) -> str:
	if not text:
		return ""
	cleaned = _TOKEN_RE.sub("EAA[REDACTED]", str(text))
	return _CODE_RE.sub(r"\1[REDACTED]", cleaned)


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
		}
	doc = frappe.get_single(SETTINGS_DOCTYPE)
	app_id = (doc.app_id or "").strip()
	config_id = (doc.config_id or "").strip()
	version = (doc.graph_api_version or GRAPH_DEFAULT).strip() or GRAPH_DEFAULT
	has_secret = bool(_read_secret(doc))
	ready = bool(doc.enabled and app_id and config_id and has_secret)
	return {
		"enabled": bool(doc.enabled),
		"ready": ready,
		"app_id": app_id or "752752485429112",
		"config_id": config_id,
		"graph_api_version": version,
		"has_secret": has_secret,
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
	if not waba_id or not phone_number_id:
		found = discover_assets(token, settings["app_id"], settings["app_secret"], settings["graph_api_version"])
		waba_id = waba_id or found.get("waba_id") or ""
		phone_number_id = phone_number_id or found.get("phone_number_id") or ""
	if not waba_id.isdigit() or not phone_number_id.isdigit():
		frappe.throw(_("Embedded Signup did not return a WhatsApp account ID and phone number ID."))

	warnings: list[str] = []
	try:
		subscribe_app(waba_id, token, settings["graph_api_version"])
	except EmbeddedSignupError as exc:
		warnings.append(str(exc))

	pin = make_pin()
	try:
		register_phone(phone_number_id, token, pin, settings["graph_api_version"])
	except EmbeddedSignupError as exc:
		warnings.append(str(exc))

	account = _upsert_account(
		account_name=account_name or f"WhatsApp {phone_number_id[-4:]}",
		phone_id=phone_number_id,
		business_id=waba_id,
		access_token=token,
		app_id=settings["app_id"],
		pin=pin,
	)
	return {
		"status": "success",
		"account": account,
		"account_name": account_name or f"WhatsApp {phone_number_id[-4:]}",
		"phone_number_id": phone_number_id,
		"waba_id": waba_id,
		"pin": pin,
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


def discover_assets(token: str, app_id: str, app_secret: str, version: str) -> dict[str, str]:
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
	if waba_id:
		numbers = _graph(
			"GET",
			f"https://graph.facebook.com/{version}/{waba_id}/phone_numbers",
			token=token,
		)
		rows = (numbers or {}).get("data") or []
		if rows:
			phone_number_id = str(rows[0].get("id") or "")
	return {"waba_id": waba_id, "phone_number_id": phone_number_id}


def subscribe_app(waba_id: str, token: str, version: str) -> None:
	_graph(
		"POST",
		f"https://graph.facebook.com/{version}/{waba_id}/subscribed_apps",
		token=token,
	)


def register_phone(phone_number_id: str, token: str, pin: str, version: str) -> None:
	_graph(
		"POST",
		f"https://graph.facebook.com/{version}/{phone_number_id}/register",
		token=token,
		payload={"messaging_product": "whatsapp", "pin": pin},
	)


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
	if hasattr(doc, "get_password"):
		try:
			return (doc.get_password("app_secret", raise_exception=False) or "").strip()
		except Exception:
			return ""
	return (getattr(doc, "app_secret", None) or "").strip()


def _graph(method: str, url: str, params: dict | None = None, payload: dict | None = None, token: str | None = None) -> dict:
	headers = {}
	if token:
		headers["Authorization"] = f"Bearer {token}"
	try:
		response = requests.request(method, url, params=params, json=payload, headers=headers, timeout=30)
	except requests.RequestException as exc:
		raise EmbeddedSignupError(_("Could not reach Meta: {0}").format(redact(str(exc)))) from exc
	try:
		body = response.json()
	except ValueError:
		body = {}
	if response.status_code >= 400 or (isinstance(body, dict) and body.get("error")):
		message = ""
		if isinstance(body, dict) and isinstance(body.get("error"), dict):
			message = body["error"].get("message") or ""
		raise EmbeddedSignupError(redact(message or response.text or f"Meta returned HTTP {response.status_code}"))
	return body if isinstance(body, dict) else {}


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
	if frappe.get_meta("WA Account").get_field("two_step_pin"):
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
