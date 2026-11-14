# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Send an ERPNext-triggered template through the WhatsApp account that lives on Nudge."""

from __future__ import annotations

from typing import Any

import frappe
import requests
from frappe import _

from nudg.integrations.erpnext.payload import classify_transport_failure


class DeliveryError(Exception):
	def __init__(self, message: str, kind: str, message_id: str = ""):
		super().__init__(message)
		self.kind = kind
		self.message_id = message_id


def deliver_template(
	*,
	account: str,
	template: str,
	recipient: str,
	body_parameters: dict[str, str],
	preview: str,
) -> dict[str, str]:
	"""Send with the account's Meta client and store a WA Message for the inbox.

	The remote Sales Invoice is not a document on this site, so the official
	send path cannot be given that reference. The message row is inserted
	after Meta accepts it, which keeps it in the Nudge chat without a second send.
	"""
	if not account or not frappe.db.exists("WA Account", account):
		raise DeliveryError(_("The WhatsApp account for this ERPNext site is not on Nudge."), "permanent")
	account_doc = frappe.get_doc("WA Account", account)
	if account_doc.status and account_doc.status != "Active":
		raise DeliveryError(_("The WhatsApp account {0} is not active.").format(account), "permanent")
	if not frappe.db.exists("WA Template", template):
		raise DeliveryError(_("Template {0} does not exist on Nudge.").format(template), "permanent")
	template_doc = frappe.get_doc("WA Template", template)
	if template_doc.status != "Approved":
		raise DeliveryError(
			_("Template {0} is {1}. Only an approved template can be sent.").format(template, template_doc.status),
			"permanent",
		)
	if template_doc.whatsapp_account and template_doc.whatsapp_account != account:
		raise DeliveryError(_("Template {0} belongs to a different WhatsApp account.").format(template), "permanent")

	from whatsapp.whatsapp.doctype.wa_message.wa_message import _get_whatsapp_client
	from whatsapp.whatsapp.doctype.wa_profile.wa_profile import get_or_create_profile
	from whatsapp.whatsapp.api.utils import build_template_message_payload

	profile = get_or_create_profile(phone_number=recipient, account_name=account, profile_name=recipient, wa_id=recipient)
	profile_doc = frappe.get_doc("WA Profile", profile)
	if profile_doc.status == "Blocked":
		raise DeliveryError(_("The recipient has blocked this WhatsApp account."), "permanent")

	settings = frappe.get_single("WA Settings")
	client = _get_whatsapp_client(account_doc, settings)
	payload = build_template_message_payload(
		to=profile_doc.phone_number,
		template_doc=template_doc,
		body_parameters=body_parameters or None,
	)
	try:
		result = client.send_message(payload)
	except requests.RequestException as exc:
		raise DeliveryError(str(exc)[:300], classify_transport_failure(exc)) from exc
	except Exception as exc:
		raise DeliveryError(str(exc)[:300], "permanent") from exc

	messages = (result or {}).get("messages") if isinstance(result, dict) else None
	message_id = ""
	if messages:
		message_id = str(messages[0].get("id") or "")
	if not message_id:
		raise DeliveryError(_("Meta accepted the call but did not return a message id."), "uncertain")

	try:
		row = _store_sent_message(
			account=account,
			profile=profile,
			template=template,
			template_name=template_doc.template_name,
			body_parameters=body_parameters,
			message_id=message_id,
			preview=preview,
		)
	except Exception as exc:
		raise DeliveryError(
			_("The message was sent, but it could not be stored in the inbox: {0}").format(str(exc)[:180]),
			"uncertain",
			message_id=message_id,
		) from exc
	return {"message_name": row, "message_id": message_id}


def _store_sent_message(
	*,
	account: str,
	profile: str,
	template: str,
	template_name: str,
	body_parameters: dict[str, str],
	message_id: str,
	preview: str,
) -> str:
	doc = frappe.new_doc("WA Message")
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_validate = True
	doc.update(
		{
			"to": profile,
			"direction": "Outgoing",
			"whatsapp_account": account,
			"is_template": 1,
			"whatsapp_template": template,
			"message": preview[:1000] or f"Template {template_name}",
			"template_body_parameters": frappe.as_json(body_parameters or {}),
			"status": "Sent",
			"message_id": message_id,
			"docstatus": 1,
		}
	)
	doc.db_insert()
	return doc.name


def ordered_body_parameters(template_doc: Any, values_by_field: dict[str, str], fields: list[str]) -> dict[str, str]:
	"""Map ERP fields onto the template's variable names, in child-table order."""
	names = []
	for row in template_doc.get("template_variables") or []:
		variable_name = row.get("variable_name") if isinstance(row, dict) else row.variable_name
		if variable_name:
			names.append(variable_name)
	if names:
		params = {}
		for index, variable_name in enumerate(names):
			field = fields[index] if index < len(fields) else ""
			params[variable_name] = values_by_field.get(field, "") if field else ""
		return params
	return {str(index + 1): values_by_field.get(field, "") for index, field in enumerate(fields)}
