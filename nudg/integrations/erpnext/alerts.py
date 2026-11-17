# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Create document alerts on a connected ERPNext site.

Nudg reads document types from that site and installs one Webhook for each
document event the user picks. The rule is not stored on Nudg.
"""

from __future__ import annotations

import json
from typing import NoReturn

import frappe
from frappe import _
from frappe.utils import get_url

from nudg.integrations.erpnext.client import ERPNextClientError
from nudg.integrations.erpnext.payload import (
	ALLOWED_EVENTS,
	RECEIVE_PATH,
	SUBMIT_EVENTS,
	PayloadError,
	alert_from_webhook,
	assert_doctype_name,
	assert_field_name,
	assert_plain_label,
	assert_variable_name,
	webhook_document,
	webhook_document_name,
	webhook_update,
)
from nudg.integrations.erpnext.service import _client_for_site, _require_site

PHONE_FIELDTYPES = frozenset({"Phone", "Data", "Read Only", "Small Text"})


def list_doctypes(site: str, query: str | None = None) -> list[dict]:
	text = _search_text(query)
	client = _client(site)
	try:
		result = client.call_method(
			"frappe.desk.search.search_link",
			{
				"doctype": "DocType",
				"txt": text,
				"page_length": 10,
				"filters": {"istable": 0, "issingle": 0},
			},
		)
	except ERPNextClientError as exc:
		_raise_remote(exc, _("Nudg could not read document types from that ERPNext site."))
	return _link_rows(result)


def describe_doctype(site: str, doctype: str) -> dict:
	doctype = assert_doctype_name(doctype)
	return _describe(_client(site), doctype)


def list_templates(site: str) -> list[dict]:
	view = _require_site(site)
	if not frappe.db.exists("DocType", "WA Template"):
		return []
	rows = frappe.get_list(
		"WA Template",
		filters={"status": "Approved", "whatsapp_account": view.whatsapp_account},
		fields=["name", "template_label", "template_name", "message", "header_text", "header_type", "footer"],
		order_by="template_label asc",
		limit_page_length=20,
	)
	names = [row.name for row in rows]
	templates = rows
	variables = _template_variables(names)
	return [
		{
			"name": row.name,
			"label": row.template_label or row.template_name or row.name,
			"template_name": row.template_name,
			"message": row.message or "",
			"header_text": row.header_text or "",
			"header_type": row.header_type or "Text",
			"footer": row.footer or "",
			"variables": variables.get(row.name, []),
		}
		for row in templates
	]


def list_alerts(site: str) -> list[dict]:
	view = _require_site(site)
	client = _client(site)
	try:
		rows = client.get_resources(
			"Webhook",
			fields=["name", "webhook_doctype", "webhook_docevent", "enabled", "request_url", "webhook_json"],
			filters=[["request_url", "like", f"%{RECEIVE_PATH}%"]],
			limit=20,
		)
	except ERPNextClientError as exc:
		_raise_remote(exc, _("Nudg could not read alerts from that ERPNext site."))
	alerts = []
	for row in rows:
		if not isinstance(row, dict):
			continue
		alert = alert_from_webhook(row, view.name)
		if (
			alert is None
			and not row.get("webhook_json")
			and row.get("name")
			and RECEIVE_PATH in str(row.get("request_url") or "")
		):
			try:
				full = client.get_resource("Webhook", str(row.get("name")))
			except ERPNextClientError as exc:
				_raise_remote(exc, _("Nudg could not read alerts from that ERPNext site."))
			alert = alert_from_webhook(full, view.name)
		if alert:
			alerts.append(alert)
	return alerts


def create_alert(
	site: str,
	doctype: str,
	event: str,
	phone_field: str,
	template: str,
	variable_map: dict | str | None = None,
) -> dict:
	view = _require_site(site)
	if view.status != "Connected":
		frappe.throw(_("Enable the ERPNext connection before adding an alert."))
	try:
		doctype = assert_doctype_name(doctype)
		phone_field = assert_field_name(phone_field, "Phone field")
		template = assert_plain_label(template, "Template")
		if event not in ALLOWED_EVENTS:
			raise PayloadError("Choose a document event Nudg can receive.")
		mapping = _ordered_mapping(template, _mapping(variable_map))
	except PayloadError as exc:
		frappe.throw(str(exc))

	_require_template(view.whatsapp_account, template, mapping)
	client = _client(site)
	described = _describe(client, doctype)
	if event in SUBMIT_EVENTS and not described["is_submittable"]:
		frappe.throw(_("That document type cannot be submitted. Choose another event."))
	fieldnames = {row["fieldname"] for row in described["fields"]}
	if phone_field not in fieldnames:
		frappe.throw(_("Choose a phone field from that document type."))
	missing = [field for field in mapping.values() if field not in fieldnames]
	if missing:
		frappe.throw(_("Choose document fields for each template variable."))

	try:
		secret = view.get_password("inbound_secret")
	except Exception:
		secret = ""
	name = webhook_document_name(view.name, f"{doctype} {event}")
	try:
		document = webhook_document(
			name=name,
			site_name=view.name,
			doctype=doctype,
			event=event,
			phone_field=phone_field,
			template=template,
			variables=mapping,
			request_url=_receive_url(),
			secret=secret,
		)
	except PayloadError as exc:
		frappe.throw(str(exc))

	try:
		existing = client.get_resource("Webhook", name)
		if existing:
			document["enabled"] = 1 if existing.get("enabled") in {1, True, "1"} else 0
			saved = client.update_resource("Webhook", name, webhook_update(document))
		else:
			saved = client.insert_resource("Webhook", document)
	except ERPNextClientError as exc:
		_raise_remote(exc, _("Nudg could not save that alert on the ERPNext site."))
	alert = alert_from_webhook(saved, view.name)
	if alert:
		return alert
	return {
		"name": name,
		"doctype": doctype,
		"event": event,
		"template": template,
		"phone_field": phone_field,
		"enabled": True,
	}


def set_alert_enabled(site: str, alert: str, enabled: bool) -> dict:
	view, client, current = _owned_alert(site, alert)
	try:
		saved = client.update_resource("Webhook", current["name"], {"enabled": 1 if enabled else 0})
	except ERPNextClientError as exc:
		_raise_remote(exc, _("Nudg could not update that alert on the ERPNext site."))
	found = alert_from_webhook({**current, **saved, "enabled": 1 if enabled else 0}, view.name)
	return found or {**current, "enabled": bool(enabled)}


def delete_alert(site: str, alert: str) -> dict:
	_view, client, current = _owned_alert(site, alert)
	try:
		client.delete_resource("Webhook", current["name"])
	except ERPNextClientError as exc:
		_raise_remote(exc, _("Nudg could not delete that alert on the ERPNext site."))
	return {"ok": True, "name": current["name"]}


def _owned_alert(site: str, alert: str):
	view = _require_site(site)
	try:
		name = assert_plain_label(alert, "Alert")
	except PayloadError as exc:
		frappe.throw(str(exc))
	client = _client(site)
	try:
		row = client.get_resource("Webhook", name)
	except ERPNextClientError as exc:
		_raise_remote(exc, _("Nudg could not read that alert on the ERPNext site."))
	current = alert_from_webhook(row, view.name)
	if current is None:
		frappe.throw(_("That alert is not on this ERPNext connection."))
	return view, client, current


def _describe(client, doctype: str) -> dict:
	try:
		doc = client.get_resource("DocType", doctype)
	except ERPNextClientError as exc:
		_raise_remote(exc, _("Nudg could not read that document type from the ERPNext site."))
	if not doc:
		frappe.throw(_("That document type was not found on the ERPNext site."))
	fields = []
	for row in doc.get("fields") or []:
		if not isinstance(row, dict):
			continue
		fieldtype = str(row.get("fieldtype") or "")
		if fieldtype not in PHONE_FIELDTYPES:
			continue
		try:
			fieldname = assert_field_name(str(row.get("fieldname") or ""), "Field")
		except PayloadError:
			continue
		fields.append(
			{
				"fieldname": fieldname,
				"label": str(row.get("label") or fieldname),
				"fieldtype": fieldtype,
			}
		)
	fields.sort(key=lambda row: (row["fieldtype"] != "Phone", row["label"].lower(), row["fieldname"]))
	submittable = doc.get("is_submittable") in {1, True, "1"}
	events = ["after_insert", "on_update"]
	if submittable:
		events.extend(["on_submit", "on_cancel"])
	visible_fields = fields[:200]
	return {
		"name": doctype,
		"is_submittable": submittable,
		"events": events,
		"fields": visible_fields,
		"sample": _sample_values(client, doctype, [row["fieldname"] for row in visible_fields]),
	}


def _sample_values(client, doctype: str, fieldnames: list[str]) -> dict[str, str]:
	"""One recent document, so the preview can show real field values."""
	if not fieldnames:
		return {}
	try:
		rows = client.get_resources(doctype, fields=["name"], limit=1)
		if not rows or not rows[0].get("name"):
			return {}
		document = client.get_resource(doctype, str(rows[0]["name"])) or {}
	except ERPNextClientError:
		return {}
	values: dict[str, str] = {}
	for fieldname in fieldnames:
		value = document.get(fieldname)
		if value in (None, ""):
			continue
		text = value if isinstance(value, str) else str(value)
		text = " ".join(text.split())
		if text:
			values[fieldname] = text[:80]
	return values


def _require_template(account: str, template: str, mapping: dict[str, str]) -> None:
	if not frappe.db.exists("WA Template", template):
		frappe.throw(_("Choose an approved WhatsApp template."))
	doc = frappe.get_doc("WA Template", template)
	if doc.status != "Approved":
		frappe.throw(_("Template {0} is not approved.").format(template))
	if doc.whatsapp_account and doc.whatsapp_account != account:
		frappe.throw(_("Template {0} belongs to a different WhatsApp account.").format(template))
	names = [row.variable_name for row in (doc.get("template_variables") or []) if row.variable_name]
	if set(mapping) != set(names):
		frappe.throw(_("Map each template variable to a field on that document."))


def _ordered_mapping(template: str, mapping: dict[str, str]) -> dict[str, str]:
	if not frappe.db.exists("WA Template", template):
		return mapping
	doc = frappe.get_doc("WA Template", template)
	names = [row.variable_name for row in (doc.get("template_variables") or []) if row.variable_name]
	if not names:
		return mapping
	return {name: mapping[name] for name in names if name in mapping}


def _template_variables(names: list[str]) -> dict[str, list[dict]]:
	if not names or not frappe.db.exists("DocType", "WA Template Variable"):
		return {}
	rows = frappe.get_all(
		"WA Template Variable",
		filters={"parent": ["in", names], "parenttype": "WA Template"},
		fields=["parent", "variable_name", "variable_example", "idx"],
		order_by="idx asc",
		limit_page_length=400,
	)
	grouped: dict[str, list[dict]] = {}
	for row in rows:
		if row.variable_name:
			grouped.setdefault(row.parent, []).append(
				{"name": row.variable_name, "example": row.variable_example or ""}
			)
	return grouped


def _mapping(value: dict | str | None) -> dict[str, str]:
	if not value:
		return {}
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except json.JSONDecodeError as exc:
			raise PayloadError("Template variables must be a field mapping.") from exc
	if not isinstance(value, dict):
		raise PayloadError("Template variables must be a field mapping.")
	cleaned = {}
	for key, field in value.items():
		cleaned[assert_variable_name(str(key))] = assert_field_name(str(field or ""), "Variable field")
	return cleaned


def _search_text(query: str | None) -> str:
	text = (query or "").strip()[:80]
	if any(char in text for char in "{}\r\n"):
		frappe.throw(_("The document type search contains characters that are not allowed."))
	return text


def _client(site: str):
	view = _require_site(site)
	client = _client_for_site(view)
	if client is None:
		frappe.throw(_("The API key for this ERPNext site is missing."))
	return client


def _receive_url() -> str:
	return get_url().rstrip("/") + RECEIVE_PATH


def _link_rows(result) -> list[dict]:
	rows = result.get("message") if isinstance(result, dict) else result
	if not isinstance(rows, list):
		return []
	cleaned = []
	seen = set()
	for row in rows:
		if isinstance(row, dict):
			name = str(row.get("value") or row.get("name") or "").strip()
			description = str(row.get("description") or "")
		else:
			continue
		try:
			name = assert_doctype_name(name)
		except PayloadError:
			continue
		if name in seen:
			continue
		seen.add(name)
		cleaned.append({"name": name, "description": description})
	return cleaned


def _raise_remote(exc: ERPNextClientError, fallback: str) -> NoReturn:
	if exc.status_code in {401, 403}:
		frappe.throw(
			_(
				"The API user on that ERPNext site is not allowed to do this. "
				"They need permission to read DocType and to create Webhook."
			)
		)
	if exc.status_code == 404:
		frappe.throw(_("That record was not found on the ERPNext site."))
	detail = str(exc).strip()
	if exc.status_code in {400, 417} and detail and "<" not in detail:
		frappe.throw(detail[:300])
	frappe.throw(fallback)
