# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Sign in to Nudg with Facebook.

Uses Frappe's Social Login Key. Google is a later provider and is not created here.
Connecting a WhatsApp number stays on Embedded Signup.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils import cint, get_url

PROVIDER = "facebook"
PROVIDER_LABEL = "Facebook"
REDIRECT_PATH = "/api/method/frappe.integrations.oauth2_logins.login_via_facebook"
GRAPH_VERSION = "v23.0"
API_ENDPOINT = f"/{GRAPH_VERSION}/me"
API_FIELDS = json.dumps({"fields": "id,first_name,last_name,email,picture"})
STOCK_ENDPOINT = "/v2.5/me"
STOCK_FIELDS = json.dumps({"fields": "first_name,last_name,email,gender,location,verified,picture"})
WHATSAPP_ROLES = {"WhatsApp User", "WhatsApp Manager", "System Manager"}
DEFAULT_LANDINGS = {"/desk/workspace", "/desk", "/apps", "/me", "/app", "/portal"}


def role_to_grant(providers, roles) -> str | None:
	"""WhatsApp User for a new Facebook account that has no Nudg role yet."""
	if PROVIDER not in set(providers or []):
		return None
	if WHATSAPP_ROLES & set(roles or []):
		return None
	return "WhatsApp User"


def nudg_landing(location: str | None) -> str | None:
	"""Send the default post-login page to Nudg. Keep an explicit redirect."""
	if not location:
		return None
	path = (urlparse(location).path or "/").rstrip("/") or "/"
	if path in DEFAULT_LANDINGS:
		return "/nudg"
	return None


def describe(doc, has_secret: bool, redirect_uri: str) -> dict:
	enabled = bool(cint(getattr(doc, "enable_social_login", 0)))
	app_id = (getattr(doc, "client_id", None) or "").strip()
	return {
		"enabled": enabled,
		"ready": bool(enabled and app_id and has_secret),
		"app_id": app_id,
		"has_secret": bool(has_secret),
		"redirect_uri": redirect_uri,
		"provider": PROVIDER,
	}


def apply_settings(doc, app_id: str | None, app_secret: str | None, enabled: bool, has_secret: bool) -> None:
	app_id = (app_id or "").strip()
	secret = (app_secret or "").strip()
	if app_id and not app_id.isdigit():
		frappe.throw(_("Enter the numeric Facebook App ID."))
	if enabled and not app_id:
		frappe.throw(_("Enter the numeric Facebook App ID."))
	if enabled and not secret and not has_secret:
		frappe.throw(_("Enter the Facebook app secret."))
	doc.client_id = app_id
	if secret:
		doc.client_secret = secret
	doc.enable_social_login = 1 if enabled else 0
	doc.sign_ups = "Allow" if enabled else "Deny"
	_use_current_graph(doc)


def grant_new_facebook_user(doc) -> None:
	"""Give a Facebook-created user access to Nudg. Existing users are left alone."""
	if not getattr(doc, "name", None) or doc.name in ("Administrator", "Guest"):
		return
	providers = [getattr(row, "provider", None) for row in (getattr(doc, "social_logins", None) or [])]
	roles = [getattr(row, "role", None) for row in (getattr(doc, "roles", None) or [])]
	if role_to_grant(providers, roles) != "WhatsApp User":
		return
	if not frappe.db.exists("Role", "WhatsApp User"):
		return
	doc.flags.ignore_permissions = True
	doc.flags.no_welcome_mail = True
	doc.add_roles("WhatsApp User")


def ensure_facebook_login(seed: bool = False) -> None:
	"""Create the Facebook Social Login Key.

	``seed`` copies the Embedded Signup app the first time this runs on migrate.
	Opening settings does not turn a disabled login back on.
	"""
	if not getattr(getattr(frappe, "local", None), "db", None):
		return
	if not frappe.db.exists("DocType", "Social Login Key"):
		return
	if frappe.db.exists("Social Login Key", PROVIDER):
		doc = frappe.get_doc("Social Login Key", PROVIDER)
		if _use_current_graph(doc):
			doc.save(ignore_permissions=True)
	else:
		doc = _new_key()
		doc.insert(ignore_permissions=True)
	if seed:
		_seed_from_signup(doc)


def public_config() -> dict:
	doc = _load_key()
	return describe(doc, _has_secret(doc), get_url(REDIRECT_PATH))


def save_settings(app_id: str | None, app_secret: str | None = None, enabled: int | bool | None = 1) -> dict:
	doc = _load_key()
	apply_settings(doc, app_id, app_secret, bool(cint(enabled)), _has_secret(doc))
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return describe(doc, _has_secret(doc), get_url(REDIRECT_PATH))


def login_via_facebook(code: str, state: str):
	"""Frappe's Facebook callback, then open Nudg instead of Desk."""
	if not _login_enabled():
		frappe.throw(_("Login with Facebook is turned off."), frappe.PermissionError)
	from frappe.integrations.oauth2_logins import login_via_facebook as frappe_login

	frappe_login(code, state)
	location = nudg_landing((getattr(frappe.local, "response", None) or {}).get("location"))
	if location:
		frappe.local.response["location"] = location


def _login_enabled() -> bool:
	if not frappe.db.exists("Social Login Key", PROVIDER):
		return False
	return bool(cint(frappe.db.get_value("Social Login Key", PROVIDER, "enable_social_login")))


def _load_key():
	ensure_facebook_login()
	if not frappe.db.exists("Social Login Key", PROVIDER):
		frappe.throw(_("Facebook login could not be prepared on this site."))
	return frappe.get_doc("Social Login Key", PROVIDER)


def _new_key():
	doc = frappe.new_doc("Social Login Key")
	doc.social_login_provider = PROVIDER_LABEL
	doc.get_social_login_provider(PROVIDER_LABEL, initialize=True)
	doc.enable_social_login = 0
	doc.sign_ups = "Deny"
	_use_current_graph(doc)
	return doc


def _use_current_graph(doc) -> bool:
	changed = False
	endpoint = (getattr(doc, "api_endpoint", None) or "").strip()
	if endpoint in ("", STOCK_ENDPOINT):
		doc.api_endpoint = API_ENDPOINT
		changed = True
	fields = (getattr(doc, "api_endpoint_args", None) or "").strip()
	if fields in ("", STOCK_FIELDS):
		doc.api_endpoint_args = API_FIELDS
		changed = True
	return changed


def _has_secret(doc) -> bool:
	if not getattr(doc, "name", None) or not frappe.db.exists("Social Login Key", doc.name):
		return bool(getattr(doc, "client_secret", None))
	from frappe.utils.password import get_decrypted_password

	return bool(get_decrypted_password("Social Login Key", doc.name, "client_secret", raise_exception=False))


def _seed_from_signup(doc) -> None:
	"""Use the Embedded Signup Meta app when Facebook login has no App ID yet."""
	if (getattr(doc, "client_id", None) or "").strip():
		return
	app_id, secret = _signup_credentials()
	if not app_id or not secret:
		return
	doc.client_id = app_id
	doc.client_secret = secret
	doc.enable_social_login = 1
	doc.sign_ups = "Allow"
	_use_current_graph(doc)
	doc.save(ignore_permissions=True)


def _signup_credentials() -> tuple[str, str]:
	from nudg.integrations.embedded_signup import SETTINGS_DOCTYPE, _read_secret

	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return "", ""
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	app_id = (getattr(settings, "app_id", None) or "").strip()
	secret = (_read_secret(settings) or "").strip()
	if app_id.isdigit() and secret:
		return app_id, secret
	return "", ""
