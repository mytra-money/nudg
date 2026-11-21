"""Read-only adapter for the official frappe/whatsapp app (v1.2.0).

This is the only module that may import ``whatsapp.*``. Imports are inside
functions so Nudg still loads when that app is absent.

Exposes installation status, ``get_messages``, ``send_message``, and
``send_template``. Catalog Meta sync lives in ``catalog_adapter``.

Official symbols this module calls, checked against the app on this bench:

- ``whatsapp.whatsapp.doctype.wa_template.wa_template.get_active_accounts()``
  requires WA Account read (``throw=True``) and returns a list of dicts with
  ``name``, ``account_name``, and ``business_id``. It does not return
  ``access_token``. The status payload keeps only the length of that list.
- ``whatsapp.whatsapp.api.messages.get_messages`` / ``send_message`` /
  ``send_template`` — permission-checked by the official app.

``frappe.db.get_single_value`` does not check permissions. ``default_account``
is read only after ``frappe.has_permission("WA Settings", "read")``. The
active-account count is read only after ``frappe.has_permission("WA Account",
"read")``. Otherwise those fields are ``None``.
"""

from __future__ import annotations

import frappe
from frappe import _

# DocTypes the desk needs from the official app. Child tables are not required.
REQUIRED_DOCTYPES = ("WA Account", "WA Settings", "WA Message")

_NOT_INSTALLED = "The official WhatsApp app is not installed on this site."
_READY = "WhatsApp is ready."


def is_installed() -> bool:
	"""True when this site's installed-app list contains ``whatsapp``."""
	return "whatsapp" in frappe.get_installed_apps()


def missing_doctypes() -> list[str]:
	"""Required official DocTypes that are not on this site, in a stable order."""
	missing = []
	for name in REQUIRED_DOCTYPES:
		if not frappe.db.exists("DocType", name):
			missing.append(name)
	return missing


def get_integration_status() -> dict:
	"""JSON-safe installation status. Does not throw when WhatsApp is absent.

	The dict never includes access tokens, webhook secrets, message bodies,
	or customer phone numbers. Account fields stay ``None`` unless the
	official app is installed, the DocType exists, and the user can read it.
	"""
	installed = is_installed()
	missing = missing_doctypes()
	dependencies = list(missing)
	if not installed:
		dependencies.insert(0, "whatsapp")

	return {
		"whatsapp_installed": installed,
		"doctypes_ready": not missing,
		"missing_dependencies": dependencies,
		"default_account": _default_account() if installed else None,
		"active_account_count": _active_account_count() if installed else None,
		"detail": _detail(installed, missing),
	}


def get_messages(references: str) -> list:
	"""Return official ``get_messages`` for a JSON list of reference pairs.

	Behavior matches a direct call. Callers that need a list when the
	official function returns nothing should keep their own ``or []``.
	"""
	from whatsapp.whatsapp.api.messages import get_messages as official_get_messages

	return official_get_messages(references)


def profile_on_account(to: str, account: str | None) -> str:
	"""Use the profile on this WhatsApp account.

	The official send looks a phone number up on the site default account.
	The same number can exist on another account, and that default is the
	wrong sender.
	"""
	if not to or not account or not frappe.db.exists("DocType", "WA Profile"):
		return to
	if frappe.db.exists("WA Profile", to):
		owner = frappe.db.get_value("WA Profile", to, "whatsapp_account")
		if owner == account:
			return to
	name = frappe.db.get_value(
		"WA Profile",
		{"whatsapp_account": account, "phone_number": to},
		"name",
	)
	return name or to


def send_message(
	to: str,
	message: str = "",
	attach: str | None = None,
	content_type: str = "text",
	reply_to: str | None = None,
	reference_doctype: str | None = None,
	reference_docname: str | None = None,
	account: str | None = None,
) -> str:
	"""Send via the official WhatsApp API. Returns the WA Message name."""
	from whatsapp.whatsapp.api.messages import send_message as official_send_message

	return official_send_message(
		to=profile_on_account(to, account),
		message=message,
		attach=attach,
		content_type=content_type,
		reply_to=reply_to,
		reference_doctype=reference_doctype,
		reference_docname=reference_docname,
	)


def _keep_supplied_template_parameters(doc) -> None:
	"""Let a campaign's body values pass the official template check.

	WA Message otherwise requires a reference document whenever the template
	lists variables, then fills those variables from that document. A campaign
	recipient already has the values, and has no reference document.
	"""
	raw = doc.template_body_parameters
	if not raw or raw in ("{}", "null"):
		return

	def _validate_template_reference() -> None:
		if doc.template_body_parameters and doc.template_body_parameters not in ("{}", "null"):
			return
		type(doc)._validate_template_reference(doc)

	doc._validate_template_reference = _validate_template_reference


def send_template(
	template: str,
	to: str,
	reference_doctype: str | None = None,
	reference_docname: str | None = None,
	components: list[dict[str, Any]] | None = None,
	language_code: str | None = None,
	account: str | None = None,
) -> str:
	"""Send an approved template via the official WhatsApp API.

	``language_code`` is accepted from connectors. Meta receives the language
	stored on the WA Template, which is the language that was approved.
	"""
	from whatsapp.whatsapp.api.messages import send_template as official_send_template

	# The template document owns the language. A caller default such as "en"
	# must not replace en_US on the approved template.
	_ = language_code

	to = profile_on_account(to, account)
	if components:
		from whatsapp.whatsapp.api.messages import (
			_resolve_to_profile,
			_submit,
			_validate_send_scope,
			_validate_template_is_approved,
		)
		_validate_send_scope(reference_doctype, reference_docname)
		_validate_template_is_approved(template)
		profile_name = _resolve_to_profile(to, create_if_missing=True)
		if not profile_name:
			frappe.throw(_("Could not resolve recipient '{0}' to a WhatsApp Profile.").format(to))

		body_params = {}
		for comp in components:
			if comp.get("type") == "body":
				for idx, p in enumerate(comp.get("parameters", []), 1):
					p_name = p.get("parameter_name") or str(idx)
					body_params[p_name] = p.get("text", "")

		doc = frappe.new_doc("WA Message")
		doc.update({
			"reference_doctype": reference_doctype,
			"reference_docname": reference_docname,
			"is_template": True,
			"message": "Template message",
			"whatsapp_template": template,
			"to": profile_name,
			"template_body_parameters": frappe.as_json(body_params),
		})
		_keep_supplied_template_parameters(doc)
		doc.insert(ignore_permissions=True)
		_submit(doc, f"Failed to send template {template} to {profile_name}")
		return doc.name

	return official_send_template(
		template=template,
		to=to,
		reference_doctype=reference_doctype,
		reference_docname=reference_docname,
	)


def ensure_local_profile(
	phone_number: str,
	account_name: str,
	profile_name: str | None = None,
	wa_id: str | None = None,
) -> str | None:
	"""Inbox identity on this site. The transcript for a connected site is stored remotely."""
	try:
		from whatsapp.whatsapp.doctype.wa_profile.wa_profile import get_or_create_profile

		return get_or_create_profile(
			phone_number=phone_number,
			account_name=account_name,
			profile_name=profile_name,
			wa_id=wa_id,
		)
	except Exception:
		frappe.log_error(title="Nudg local profile")
		return None


def deliver_text(account: str, to_phone: str, text: str) -> str:
	"""Send text through Meta and return the WhatsApp message id. Does not write a WA Message."""
	from whatsapp.whatsapp.api.utils import build_text_message_payload

	return _deliver(account, build_text_message_payload(to=_meta_phone(to_phone), text=text))


def deliver_buttons(account: str, to_phone: str, text: str, buttons: list[dict]) -> str:
	"""Send reply buttons through Meta. Does not write a WA Message."""
	from whatsapp.whatsapp.api.utils import build_interactive_buttons_payload

	payload = build_interactive_buttons_payload(
		to=_meta_phone(to_phone),
		body_text=text or "Choose an option",
		buttons=[{"id": row["id"], "title": row["title"]} for row in buttons],
	)
	return _deliver(account, payload)


def deliver_template(account: str, to_phone: str, template: str, body_parameters: dict | None = None) -> str:
	"""Send an approved template through Meta. Does not write a WA Message."""
	from whatsapp.whatsapp.api.utils import build_template_message_payload

	template_doc = frappe.get_doc("WA Template", template)
	return _deliver(
		account,
		build_template_message_payload(
			to=_meta_phone(to_phone),
			template_doc=template_doc,
			body_parameters=body_parameters or {},
		),
	)


def apply_local_webhook(field: str | None, value: dict) -> None:
	"""Official handler for one webhook change that belongs on this site's database."""
	if field == "messages":
		from whatsapp.whatsapp.webhook import _handle_messages

		_handle_messages(value)
	elif field == "message_template_status_update":
		from whatsapp.whatsapp.webhook import _handle_template_status

		_handle_template_status(value)


def _deliver(account: str, payload: dict) -> str:
	from nudg.integrations.coexistence import pace

	pace(account)
	from whatsapp.whatsapp.doctype.wa_message.wa_message import _get_whatsapp_client

	account_doc = frappe.get_doc("WA Account", account)
	settings = frappe.get_single("WA Settings")
	result = _get_whatsapp_client(account_doc, settings).send_message(payload)
	messages = (result or {}).get("messages") or []
	message_id = messages[0].get("id") if messages else ""
	if not message_id:
		frappe.throw(_("WhatsApp did not return a message id."))
	return str(message_id)


def _meta_phone(phone: str) -> str:
	digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
	return digits or str(phone or "")


def mark_as_read(message_id: str, account_name: str | None = None) -> bool:
	"""Mark an incoming WhatsApp message as read via the official Meta client."""
	if not message_id:
		return False
	try:
		from whatsapp.whatsapp.api.whatsapp import WhatsApp

		account = account_name or _default_account()
		if not account:
			return False
		client = WhatsApp(account)
		client.mark_as_read(message_id)
		return True
	except Exception:
		return False


def _can_read(doctype: str) -> bool:
	if not frappe.db.exists("DocType", doctype):
		return False
	return bool(frappe.has_permission(doctype, "read"))


def _default_account() -> str | None:
	if not _can_read("WA Settings"):
		return None
	value = frappe.db.get_single_value("WA Settings", "default_account")
	if not value:
		return None
	return str(value)


def _active_account_count() -> int | None:
	if not _can_read("WA Account"):
		return None
	try:
		from whatsapp.whatsapp.doctype.wa_template.wa_template import get_active_accounts
	except ImportError:
		return None
	try:
		accounts = get_active_accounts()
	except frappe.PermissionError:
		return None
	return len(accounts or [])


def _detail(installed: bool, missing: list[str]) -> str:
	if not installed:
		return _NOT_INSTALLED
	if missing:
		return "WhatsApp is installed, but these DocTypes are missing: " + ", ".join(missing) + "."
	return _READY
