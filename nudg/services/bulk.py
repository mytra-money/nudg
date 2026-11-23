# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Bulk WhatsApp sends. A campaign schedule creates one of these and submits it."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

from nudg.services.campaigns import build_template_body_components, check_recipient_consent


def clean_mobile(value) -> str:
	"""Keep digits and a leading plus."""
	raw = "".join(char for char in str(value or "") if char.isdigit() or char == "+")
	if raw.count("+") > 1 or ("+" in raw and not raw.startswith("+")):
		raw = "+" + raw.replace("+", "")
	return raw


def import_rows(doctype, mobile_field, name_field=None, filters=None, limit=None, data_fields=None) -> list[dict]:
	"""Read another DocType into recipient dicts. The caller saves them."""
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else None
	if isinstance(data_fields, str):
		data_fields = json.loads(data_fields) if data_fields else None
	fields = [mobile_field]
	if name_field and name_field not in fields:
		fields.append(name_field)
	meta = frappe.get_meta(doctype)
	known = {df.fieldname for df in meta.fields}
	for field in data_fields or []:
		if field not in fields and (field in known or field in frappe.model.default_fields):
			fields.append(field)
	query = {"filters": filters or {}, "fields": fields}
	if cint(limit):
		query["limit_page_length"] = cint(limit)
	records = frappe.get_all(doctype, **query)
	rows = []
	for record in records:
		mobile = clean_mobile(record.get(mobile_field))
		if not mobile:
			continue
		data = {}
		for field in data_fields or []:
			if record.get(field) not in (None, ""):
				data[str(field).lower().replace(" ", "_")] = record.get(field)
		row = {"mobile_number": mobile, "recipient_data": json.dumps(data) if data else None}
		if name_field and record.get(name_field):
			row["recipient_name"] = record.get(name_field)
		rows.append(row)
	return rows


def recipient_rows(doc) -> list[dict]:
	if doc.recipient_type == "Recipient List" and doc.recipient_list:
		return frappe.get_all(
			"WA Recipient",
			filters={"parent": doc.recipient_list, "parenttype": "WA Recipient List"},
			fields=["mobile_number", "recipient_name", "recipient_data"],
		)
	rows = []
	for row in doc.recipients or []:
		rows.append({
			"mobile_number": row.mobile_number,
			"recipient_name": row.recipient_name,
			"recipient_data": row.recipient_data,
		})
	return rows


def queue_messages(doc):
	"""Enqueue one send per recipient. In tests the send runs immediately."""
	doc.db_set("status", "In Progress")
	for recipient in recipient_rows(doc):
		payload = {
			"mobile_number": recipient.get("mobile_number"),
			"recipient_name": recipient.get("recipient_name"),
			"recipient_data": recipient.get("recipient_data"),
		}
		if getattr(frappe.flags, "in_test", False):
			send_one(doc.name, payload)
		else:
			frappe.enqueue(
				"nudg.services.bulk.send_one",
				queue="long",
				timeout=4000,
				enqueue_after_commit=True,
				bulk_name=doc.name,
				recipient=payload,
			)


def send_one(bulk_name: str, recipient: dict):
	"""Create and send one template message for a bulk recipient."""
	if isinstance(recipient, str):
		recipient = json.loads(recipient)
	phone = clean_mobile((recipient or {}).get("mobile_number"))
	if not phone or not bulk_name:
		return
	if _already_attempted(bulk_name, phone):
		return
	_mark_attempted(bulk_name, phone)

	doc = frappe.get_doc("WA Bulk Message", bulk_name)
	if not check_recipient_consent(phone_number=phone):
		_finish(doc.name)
		return

	variables = None
	if doc.variable_type == "Unique":
		variables = recipient.get("recipient_data")
	elif doc.template_variables:
		variables = doc.template_variables
	components = build_template_body_components(variables)

	try:
		from nudg.integrations.whatsapp import adapter

		message_name = adapter.send_template(
			template=doc.template,
			to=phone,
			account=doc.whatsapp_account,
			reference_doctype="WA Bulk Message",
			reference_docname=doc.name,
			components=components,
		)
		if message_name and frappe.db.has_column("WA Message", "bulk_message"):
			frappe.db.set_value("WA Message", message_name, "bulk_message", doc.name, update_modified=False)
		_bump(doc.name, "sent_count")
	except Exception:
		frappe.log_error(title=f"Bulk WhatsApp send failed: {doc.name}")
		_bump(doc.name, "failed_count")
	_finish(doc.name)


def retry_failed(doc):
	"""Send again for WA Messages on this bulk that are Failed."""
	failed = frappe.get_all(
		"WA Message",
		filters={"bulk_message": doc.name, "status": "Failed"},
		fields=["name", "to", "whatsapp_template", "template_body_parameters"],
	)
	for message in failed:
		if getattr(frappe.flags, "in_test", False):
			resend_one(doc.name, message.name)
		else:
			frappe.enqueue(
				"nudg.services.bulk.resend_one",
				queue="long",
				timeout=4000,
				enqueue_after_commit=True,
				bulk_name=doc.name,
				message_name=message.name,
			)
	return len(failed)


def resend_one(bulk_name: str, message_name: str):
	message = frappe.get_doc("WA Message", message_name)
	phone = frappe.db.get_value("WA Profile", message.to, "phone_number") or message.to
	bulk = frappe.get_doc("WA Bulk Message", bulk_name)
	components = None
	raw = message.get("template_body_parameters")
	if raw:
		parsed = raw if isinstance(raw, dict) else json.loads(raw)
		components = [{"type": "body", "parameters": [
			{"type": "text", "parameter_name": key, "text": str(value)}
			for key, value in parsed.items()
		]}] if isinstance(parsed, dict) else None
	try:
		from nudg.integrations.whatsapp import adapter

		new_name = adapter.send_template(
			template=message.whatsapp_template or bulk.template,
			to=phone,
			reference_doctype="WA Bulk Message",
			reference_docname=bulk_name,
			components=components,
		)
		if new_name and frappe.db.has_column("WA Message", "bulk_message"):
			frappe.db.set_value("WA Message", new_name, "bulk_message", bulk_name, update_modified=False)
		frappe.db.set_value("WA Message", message_name, "status", "Sent", update_modified=False)
		_bump(bulk_name, "sent_count")
		if cint(frappe.db.get_value("WA Bulk Message", bulk_name, "failed_count")):
			frappe.db.sql(
				"update `tabWA Bulk Message` set failed_count = greatest(ifnull(failed_count, 0) - 1, 0) where name = %s",
				bulk_name,
			)
	except Exception:
		frappe.log_error(title=f"Bulk WhatsApp retry failed: {message_name}")
	_finish(bulk_name)


def get_progress(name: str) -> dict:
	doc = frappe.get_doc("WA Bulk Message", name)
	total = cint(doc.recipient_count)
	sent = _count(name, ("Sent", "Delivered", "Read"))
	failed = _count(name, ("Failed",))
	queued = _count(name, ("Pending", "Queued"))
	return {
		"total": total,
		"sent": sent,
		"failed": failed,
		"queued": queued,
		"percent": (sent / total * 100) if total else 0,
	}


def process_scheduled_bulk_messages():
	"""Claim due scheduled bulk messages, then queue their recipients."""
	if not frappe.db.exists("DocType", "WA Bulk Message"):
		return []
	due = frappe.get_all(
		"WA Bulk Message",
		filters={"status": "Scheduled", "docstatus": 1, "scheduled_time": ["<=", now_datetime()]},
		pluck="name",
	)
	started = []
	for name in due:
		try:
			frappe.db.set_value("WA Bulk Message", name, "status", "Queued")
			queue_messages(frappe.get_doc("WA Bulk Message", name))
			if not getattr(frappe.flags, "in_test", False):
				frappe.db.commit()
			started.append(name)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Scheduled bulk message failed: {name}")
	return started


def sync_message_status(doc, method=None):
	"""Keep bulk sent/failed counts aligned when Meta reports a status."""
	bulk_name = None
	try:
		if frappe.db.has_column("WA Message", "bulk_message"):
			bulk_name = doc.get("bulk_message")
	except Exception:
		return
	if not bulk_name:
		return
	_finish(bulk_name)


def mpm_action(doc) -> dict | None:
	"""Meta multi-product action, capped at 30 products."""
	if not doc.whatsapp_account or not doc.thumbnail_product_retailer_id or not doc.product_ids:
		return None
	product_list = list(dict.fromkeys(part.strip() for part in str(doc.product_ids).split(",") if part.strip()))
	if len(product_list) > 30:
		product_list = product_list[:30]
		frappe.msgprint(_("Only the first 30 products were included."), indicator="orange")
	return {
		"thumbnail_product_retailer_id": doc.thumbnail_product_retailer_id,
		"sections": [{
			"title": doc.mpm_header or "Our Products",
			"product_items": [{"product_retailer_id": product_id} for product_id in product_list],
		}],
	}


def _count(name, statuses) -> int:
	if not frappe.db.has_column("WA Message", "bulk_message"):
		return 0
	return frappe.db.count("WA Message", {"bulk_message": name, "status": ["in", list(statuses)]})


def _bump(name: str, field: str):
	if field not in ("sent_count", "failed_count"):
		return
	frappe.db.sql(
		f"update `tabWA Bulk Message` set `{field}` = ifnull(`{field}`, 0) + 1 where name = %s",
		name,
	)


def _finish(name: str):
	row = frappe.db.get_value(
		"WA Bulk Message",
		name,
		["recipient_count", "sent_count", "failed_count", "status"],
		as_dict=True,
	)
	if not row:
		return
	done = cint(row.sent_count) + cint(row.failed_count)
	if done < cint(row.recipient_count):
		if row.status not in ("In Progress", "Partially Failed"):
			frappe.db.set_value("WA Bulk Message", name, "status", "In Progress", update_modified=False)
		return
	if cint(row.failed_count) and cint(row.sent_count):
		status = "Partially Failed"
	elif cint(row.failed_count) and not cint(row.sent_count):
		status = "Failed"
	else:
		status = "Completed"
	frappe.db.set_value("WA Bulk Message", name, "status", status, update_modified=False)


def _attempt_key(bulk_name: str, phone: str) -> str:
	return f"nudg-bulk:{bulk_name}:{phone}"


def _already_attempted(bulk_name: str, phone: str) -> bool:
	try:
		return bool(frappe.cache().get_value(_attempt_key(bulk_name, phone)))
	except Exception:
		return False


def _mark_attempted(bulk_name: str, phone: str):
	try:
		frappe.cache().set_value(_attempt_key(bulk_name, phone), 1, expires_in_sec=7 * 24 * 3600)
	except Exception:
		pass


@frappe.whitelist()
def get_bulk_progress(name: str):
	frappe.has_permission("WA Bulk Message", "read", throw=True)
	return get_progress(name)


@frappe.whitelist()
def retry_failed_messages(name: str):
	doc = frappe.get_doc("WA Bulk Message", name)
	frappe.has_permission("WA Bulk Message", "write", doc=doc, throw=True)
	count = retry_failed(doc)
	return {"requeued": count}


@frappe.whitelist()
def import_recipients(list_name, doctype, mobile_field, name_field=None, filters=None, limit=None, data_fields=None):
	doc = frappe.get_doc("WA Recipient List", list_name)
	frappe.has_permission("WA Recipient List", "write", doc=doc, throw=True)
	if isinstance(filters, str) and filters:
		filters = json.loads(filters)
	if isinstance(data_fields, str) and data_fields:
		data_fields = json.loads(data_fields)
	count = doc.import_list_from_doctype(doctype, mobile_field, name_field, filters, limit, data_fields)
	doc.save()
	return count


def validate_schedule(scheduled_time):
	if scheduled_time and get_datetime(scheduled_time) <= now_datetime():
		frappe.throw(_("Scheduled time must be in the future"))
