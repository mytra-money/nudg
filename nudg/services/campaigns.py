# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Campaign list, scheduler, and broadcast runner with variable interpolation and funnel analytics."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import frappe
from frappe import _
from nudg.integrations.connector.factory import get_connector
from nudg.integrations.whatsapp import adapter

logger = logging.getLogger("nudg.services.campaigns")


def _redact_token_string(s: Any) -> str:
	"""Scrub Meta access tokens (EAAB...) from strings to prevent credential leakage."""
	if not s:
		return ""
	return re.sub(r"EAAB\w+", "EAAB[REDACTED]", str(s))


def list_recipient_lists(account: str | None = None) -> list[dict]:
	"""Recipient lists the marketing form can attach to a campaign."""
	if not frappe.db.exists("DocType", "WA Recipient List"):
		return []
	frappe.has_permission("WA Recipient List", "read", throw=True)
	filters = {}
	if account:
		filters["whatsapp_account"] = account
	rows = frappe.get_list(
		"WA Recipient List",
		filters=filters,
		fields=["name", "list_name", "whatsapp_account"],
		order_by="modified desc",
		limit_page_length=100,
	)
	return rows if isinstance(rows, list) else []


def list_campaigns(account: str | None = None, start: int | None = 0, limit: int | None = None) -> list[dict]:
	"""Retrieve list of campaigns with funnel metrics."""
	from nudg.paging import page_limit, page_start

	frappe.has_permission("UTM Campaign", "read", throw=True)
	filters = {}
	if account:
		filters["whatsapp_account"] = account
	raw_list = frappe.get_list(
		"UTM Campaign",
		filters=filters,
		fields=[
			"name",
			"slug",
			"campaign_description",
			"whatsapp_account",
			"whatsapp_last_error",
			"modified",
		],
		order_by="modified desc",
		limit_start=page_start(start),
		limit_page_length=page_limit(limit, default=50, maximum=50),
	)
	templates = _schedule_templates([c.name for c in raw_list])
	result = []
	for c in raw_list:
		template = templates.get(c.name)
		result.append({
			"name": c.name,
			"campaign_name": c.name,
			"slug": c.get("slug"),
			"description": c.get("campaign_description"),
			"whatsapp_account": c.get("whatsapp_account"),
			"whatsapp_channel": c.get("whatsapp_account"),
			"template": template,
			"whatsapp_template": template,
			"status": "Draft",
			"last_error": c.get("whatsapp_last_error"),
			"modified": c.modified,
		})
	return result


def get_campaign(name: str) -> dict:
	"""Fetch complete campaign document with recipients."""
	doc = frappe.get_doc("UTM Campaign", name)
	frappe.has_permission("UTM Campaign", "read", doc=doc, throw=True)
	d = doc.as_dict()
	template = _campaign_template(doc)
	d["campaign_name"] = doc.name
	d["whatsapp_channel"] = doc.get("whatsapp_account")
	d["template"] = template
	d["whatsapp_template"] = template
	d["status"] = "Draft"
	d["whatsapp_schedules"] = doc.get("whatsapp_schedules") or []
	d["last_error"] = doc.get("whatsapp_last_error")
	d["recipients"] = _recipient_rows(doc)
	return d


def build_template_body_components(variables_raw: Any) -> list[dict[str, Any]] | None:
	"""Convert recipient variables_json into Meta Cloud API template components.

	Supports:
	  1. JSON array: ["John", "ORD123"] -> [{"type": "body", "parameters": [{"type": "text", "text": "John"}, ...]}]
	  2. Positional dict: {"1": "John", "2": "ORD123"} or {"{{1}}": "John", "{{2}}": "ORD123"}
	  3. Named dict: {"name": "John", "order_id": "ORD123"} -> [{"type": "body", "parameters": [{"type": "text", "parameter_name": "name", ...}]}]
	  4. Pre-formed components dict: {"components": [...]}
	"""
	if not variables_raw:
		return None

	parsed = variables_raw
	if isinstance(variables_raw, str):
		trimmed = variables_raw.strip()
		if not trimmed:
			return None
		try:
			parsed = json.loads(trimmed)
		except Exception:
			parsed = [trimmed]

	# Allow direct component override
	if isinstance(parsed, dict) and "components" in parsed and isinstance(parsed["components"], list):
		return parsed["components"]

	parameters: list[dict[str, Any]] = []

	if isinstance(parsed, (list, tuple)):
		for val in parsed:
			parameters.append({"type": "text", "text": str(val) if val is not None else ""})
	elif isinstance(parsed, dict):
		cleaned_keys = {}
		all_numeric = True
		for k, v in parsed.items():
			clean_k = str(k).strip()
			m = re.match(r"^\{\{\s*(\w+)\s*\}\}$", clean_k)
			var_name = m.group(1) if m else clean_k
			cleaned_keys[var_name] = v
			if not var_name.isdigit():
				all_numeric = False

		if all_numeric and cleaned_keys:
			# Sort numerically so {{1}} comes before {{2}} regardless of dict key ordering
			sorted_vars = sorted(cleaned_keys.items(), key=lambda item: int(item[0]))
			for _, val in sorted_vars:
				parameters.append({"type": "text", "text": str(val) if val is not None else ""})
		else:
			for k, val in cleaned_keys.items():
				parameters.append({
					"type": "text",
					"parameter_name": str(k),
					"text": str(val) if val is not None else "",
				})
	else:
		parameters.append({"type": "text", "text": str(parsed)})

	if not parameters:
		return None

	return [{"type": "body", "parameters": parameters}]


def check_recipient_consent(profile: str | None = None, phone_number: str | None = None) -> bool:
	"""Check if recipient has opted out of WhatsApp messages.

	Returns:
		bool: True if recipient has consent to send; False if opted-out/blocked.
	"""
	# 1. Integration with consent service if available
	try:
		from nudg.services import consent
		if profile and hasattr(consent, "is_contact_opted_out") and consent.is_contact_opted_out(profile):
			return False
		if phone_number and hasattr(consent, "is_contact_opted_out") and consent.is_contact_opted_out(phone_number):
			return False
	except Exception:
		pass

	# 2. Check WA Profile
	if frappe.db.exists("DocType", "WA Profile"):
		wa_prof = None
		if profile and frappe.db.exists("WA Profile", profile):
			wa_prof = profile
		elif phone_number:
			wa_prof = frappe.db.get_value("WA Profile", {"phone_number": phone_number}, "name")
		if wa_prof:
			prof_status = frappe.db.get_value("WA Profile", wa_prof, "status")
			if str(prof_status or "").lower() in ("blocked", "opted-out", "opt-out", "unsubscribed"):
				return False

	return True


def run_campaign(name: str, claimed: int = 0) -> dict:
	"""Process Pending recipients with dynamic variable interpolation and compliance checks."""
	doc = frappe.get_doc("UTM Campaign", name)
	frappe.has_permission("UTM Campaign", "write", doc=doc, throw=True)
	status = doc.get("whatsapp_status") or doc.get("status") or "Draft"
	if status in ("Completed", "Cancelled"):
		frappe.throw(_("Campaign {0} is {1} and cannot run.").format(name, status))
	already_claimed = str(claimed) in ("1", "True", "true")
	if status == "Running" and not already_claimed:
		return {
			"name": name,
			"status": "Running",
			"already_running": True,
			"sent_count": doc.get("whatsapp_sent_count") or doc.get("sent_count") or 0,
			"delivered_count": doc.get("whatsapp_delivered_count") or doc.get("delivered_count") or 0,
			"read_count": doc.get("whatsapp_read_count") or doc.get("read_count") or 0,
			"failed_count": doc.get("whatsapp_failed_count") or doc.get("failed_count") or 0,
			"last_error": doc.get("whatsapp_last_error") or doc.get("last_error"),
		}
	template = _campaign_template(doc)
	if not template:
		frappe.throw(_("Campaign needs a template."))

	if hasattr(doc, "whatsapp_status"):
		doc.whatsapp_status = "Running"
	if hasattr(doc, "status"):
		doc.status = "Running"
	if hasattr(doc, "whatsapp_last_error"):
		doc.whatsapp_last_error = None
	if hasattr(doc, "last_error"):
		doc.last_error = None
	doc.save()

	sent = int(doc.get("whatsapp_sent_count") or doc.get("sent_count") or 0)
	failed = int(doc.get("whatsapp_failed_count") or doc.get("failed_count") or 0)

	channel = getattr(doc, "whatsapp_account", None) or getattr(doc, "whatsapp_channel", None)
	connector = None
	try:
		if channel:
			connector = get_connector(channel)
	except Exception as exc:
		logger.debug(f"Could not load provider connector for {channel}: {exc}")

	recipients = _recipient_rows(doc)
	for row in recipients:
		if row.status != "Pending":
			continue

		to = getattr(row, "phone_number", None) or getattr(row, "profile", None)
		if not to:
			row.status = "Skipped"
			row.error_message = "Missing profile or phone number"
			continue

		# Pre-send compliance check
		if not check_recipient_consent(getattr(row, "profile", None), getattr(row, "phone_number", None)):
			row.status = "Skipped: Opted Out"
			row.error_message = "Recipient has opted out of WhatsApp communications"
			continue

		# Dynamic variable interpolation
		components = build_template_body_components(getattr(row, "variables_json", None))

		try:
			if connector:
				res = connector.send_template(
					channel_doc=channel,
					to=to,
					template_name=template,
					language_code="en",
					components=components,
				)
				row.status = "Sent"
				msg_id = res.get("message_id")
				if hasattr(row, "message_id"):
					row.message_id = msg_id
				if res.get("record_name"):
					row.message = res.get("record_name")
				elif not row.message and frappe.db.exists("DocType", "WA Message") and frappe.db.exists("WA Message", msg_id):
					row.message = msg_id
				row.error_message = None
				sent += 1
			else:
				message_name = adapter.send_template(
					template=template,
					to=to,
					components=components,
				)
				row.status = "Sent"
				row.message = message_name
				if hasattr(row, "message_id"):
					row.message_id = frappe.db.get_value("WA Message", message_name, "message_id") or message_name
				row.error_message = None
				sent += 1
		except Exception as exc:
			row.status = "Failed"
			row.error_message = _redact_token_string(str(exc))[:500]
			failed += 1
			if hasattr(doc, "whatsapp_last_error"):
				doc.whatsapp_last_error = row.error_message
			if hasattr(doc, "last_error"):
				doc.last_error = row.error_message

	if hasattr(doc, "whatsapp_sent_count"):
		doc.whatsapp_sent_count = sent
	if hasattr(doc, "sent_count"):
		doc.sent_count = sent
	if hasattr(doc, "whatsapp_failed_count"):
		doc.whatsapp_failed_count = failed
	if hasattr(doc, "failed_count"):
		doc.failed_count = failed

	# Recipient rows must be stored before the funnel count, which reads them from the database.
	doc.save()
	recalculate_campaign_funnel_counts(doc)

	pending = any(r.status == "Pending" for r in recipients)
	final_status = "Failed" if (failed and not sent and not pending) else ("Scheduled" if pending else "Completed")
	schedules = doc.get("whatsapp_schedules") or []
	if schedules and any(not getattr(row, "bulk_message", None) for row in schedules) and final_status == "Completed":
		final_status = "In Progress"
	if hasattr(doc, "whatsapp_status"):
		doc.whatsapp_status = final_status
	if hasattr(doc, "status"):
		doc.status = final_status

	doc.save()

	return {
		"name": doc.name,
		"status": doc.get("whatsapp_status") or doc.get("status"),
		"sent_count": doc.get("whatsapp_sent_count") or doc.get("sent_count") or 0,
		"delivered_count": doc.get("whatsapp_delivered_count") or doc.get("delivered_count") or 0,
		"read_count": doc.get("whatsapp_read_count") or doc.get("read_count") or 0,
		"failed_count": doc.get("whatsapp_failed_count") or doc.get("failed_count") or 0,
		"last_error": doc.get("whatsapp_last_error") or doc.get("last_error"),
	}


def enqueue_run(name: str) -> dict:
	"""UTM Campaign no longer sends. WhatsApp Campaign creates the bulk message."""
	from nudg.services.campaign_schedules import send_whatsapp_campaign

	if frappe.db.exists("WA Campaign", name):
		created = send_whatsapp_campaign(name)
		return {"name": name, "queued": bool(created), "bulk_messages": created}
	frappe.throw(_("Send this from a WhatsApp Campaign. The campaign record no longer sends messages."))


def check_and_run_scheduled_campaigns(now: bool = False) -> list[str]:
	"""Create bulk messages for WhatsApp Campaigns whose start date has arrived."""
	from nudg.services.campaign_schedules import send_due_campaign_schedules

	return send_due_campaign_schedules()


def recalculate_campaign_funnel_counts(doc_or_name: Any) -> dict:
	"""Calculate Sent, Delivered, Read, and Failed counts from recipient rows."""
	campaign_name = doc_or_name.name if hasattr(doc_or_name, "name") else str(doc_or_name)

	# Aggregate counts from child recipient table
	counts = frappe.db.sql(
		"""
		SELECT
			SUM(CASE WHEN status IN ('Sent', 'Delivered', 'Read') THEN 1 ELSE 0 END) as sent_count,
			SUM(CASE WHEN status IN ('Delivered', 'Read') THEN 1 ELSE 0 END) as delivered_count,
			SUM(CASE WHEN status = 'Read' THEN 1 ELSE 0 END) as read_count,
			SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed_count
		FROM `tabWA Campaign Recipient`
		WHERE parent = %s
		""",
		(campaign_name,),
		as_dict=True,
	)

	res = {
		"sent_count": 0,
		"delivered_count": 0,
		"read_count": 0,
		"failed_count": 0,
	}
	if counts and counts[0]:
		c = counts[0]
		res["sent_count"] = int((c.get("sent_count") if isinstance(c, dict) else getattr(c, "sent_count", 0)) or 0)
		res["delivered_count"] = int((c.get("delivered_count") if isinstance(c, dict) else getattr(c, "delivered_count", 0)) or 0)
		res["read_count"] = int((c.get("read_count") if isinstance(c, dict) else getattr(c, "read_count", 0)) or 0)
		res["failed_count"] = int((c.get("failed_count") if isinstance(c, dict) else getattr(c, "failed_count", 0)) or 0)

	if hasattr(doc_or_name, "name"):
		doc_or_name.whatsapp_sent_count = res["sent_count"]
		if hasattr(doc_or_name, "whatsapp_delivered_count"):
			doc_or_name.whatsapp_delivered_count = res["delivered_count"]
		if hasattr(doc_or_name, "whatsapp_read_count"):
			doc_or_name.whatsapp_read_count = res["read_count"]
		doc_or_name.whatsapp_failed_count = res["failed_count"]
	else:
		updates: dict[str, Any] = {}
		if frappe.db.has_column("UTM Campaign", "whatsapp_sent_count"):
			updates["whatsapp_sent_count"] = res["sent_count"]
		if frappe.db.has_column("UTM Campaign", "whatsapp_failed_count"):
			updates["whatsapp_failed_count"] = res["failed_count"]
		if frappe.db.has_column("UTM Campaign", "whatsapp_delivered_count"):
			updates["whatsapp_delivered_count"] = res["delivered_count"]
		if frappe.db.has_column("UTM Campaign", "whatsapp_read_count"):
			updates["whatsapp_read_count"] = res["read_count"]
		if updates:
			frappe.db.set_value("UTM Campaign", campaign_name, updates, update_modified=False)

	return res


def update_campaign_recipient_status(
	message_id: str,
	new_status: str,
	errors: list[dict] | None = None,
) -> bool:
	"""Update child recipient status upon webhook delivery/read receipts."""
	if not message_id or not frappe.db.exists("DocType", "WA Campaign Recipient"):
		return False

	status_map = {
		"sent": "Sent",
		"delivered": "Delivered",
		"read": "Read",
		"failed": "Failed",
	}
	normalized_status = status_map.get(str(new_status).lower())
	if not normalized_status:
		return False

	# Find matching recipient row by message_id or message
	row_data = frappe.db.sql(
		"""
		SELECT name, parent, status
		FROM `tabWA Campaign Recipient`
		WHERE message_id = %s OR message = %s
		LIMIT 1
		""",
		(message_id, message_id),
		as_dict=True,
	)
	if not row_data:
		return False

	row = row_data[0]
	current_status = row.get("status") if isinstance(row, dict) else getattr(row, "status", None)
	row_name = row.get("name") if isinstance(row, dict) else getattr(row, "name", None)
	row_parent = row.get("parent") if isinstance(row, dict) else getattr(row, "parent", None)

	# Precedence guard: Read > Delivered > Sent. Never downgrade unless explicitly Failed.
	rank = {"Sent": 1, "Delivered": 2, "Read": 3, "Failed": 4}
	if current_status == "Failed" or (rank.get(current_status, 0) >= rank.get(normalized_status, 0) and normalized_status != "Failed"):
		return False

	updates: dict[str, Any] = {"status": normalized_status}
	if errors:
		raw_err = json.dumps(errors) if not isinstance(errors, str) else errors
		updates["error_message"] = _redact_token_string(raw_err)[:500]

	frappe.db.set_value("WA Campaign Recipient", row_name, updates, update_modified=False)

	# Trigger funnel count recalculation on parent campaign
	recalculate_campaign_funnel_counts(row_parent)

	frappe.publish_realtime(
		"nudg_campaign_updated",
		{
			"campaign": row_parent,
			"recipient": row_name,
			"status": normalized_status,
		},
	)
	return True


def _account_or_throw(account: str | None) -> str | None:
	"""Keep a campaign on a WhatsApp account this user is allowed to use."""
	account = (account or "").strip()
	if not account:
		return None
	if not frappe.db.exists("WA Account", account):
		frappe.throw(_("WhatsApp Account {0} was not found.").format(account))
	user = getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	if user == "Guest":
		frappe.throw(_("Log in to continue."), frappe.PermissionError)
	if user == "Administrator":
		return account
	roles = frappe.get_roles(user) if hasattr(frappe, "get_roles") else []
	if isinstance(roles, (list, tuple, set)) and "System Manager" in roles:
		return account
	from nudg.security import get_user_wa_accounts

	if account not in (get_user_wa_accounts(user) or []):
		frappe.throw(_("You cannot use WhatsApp Account {0}.").format(account), frappe.PermissionError)
	return account


def _template_or_throw(template: str | None) -> str | None:
	template = (template or "").strip()
	if not template:
		return None
	if not frappe.db.exists("WA Template", template):
		frappe.throw(_("WhatsApp Template {0} was not found.").format(template))
	return template


def _unique_slug(label: str, ignore: str | None = None) -> str:
	base = re.sub(r"[^a-z0-9]+", "-", (label or "").strip().lower()).strip("-") or "campaign"
	base = base[:120]
	slug = base
	for n in range(2, 60):
		existing = frappe.db.get_value("UTM Campaign", {"slug": slug}, "name")
		if not existing or existing == ignore:
			return slug
		slug = f"{base}-{n}"
	return f"{base}-{frappe.generate_hash(length=6)}"


def create_campaign(
	name: str,
	campaign_description: str | None = None,
	whatsapp_account: str | None = None,
	whatsapp_template: str | None = None,
	schedules: Any = None,
) -> dict:
	"""Create a draft UTM Campaign. Audience and dates live on WhatsApp Campaign."""
	frappe.has_permission("UTM Campaign", "create", throw=True)
	name = (name or "").strip()
	if not name:
		frappe.throw(_("Campaign name is required."))
	if frappe.db.exists("UTM Campaign", name):
		frappe.throw(_("A campaign named {0} already exists.").format(name))
	account = _account_or_throw(whatsapp_account)
	template = _template_or_throw(whatsapp_template)
	doc = frappe.get_doc(
		{
			"doctype": "UTM Campaign",
			"name": name,
			"slug": _unique_slug(name),
			"campaign_description": (campaign_description or "").strip(),
			"whatsapp_account": account,
		}
	)
	_apply_campaign_plan(doc, schedules=schedules, whatsapp_template=template)
	doc.insert()
	return get_campaign(doc.name)


def update_campaign(
	name: str,
	campaign_name: str | None = None,
	campaign_description: str | None = None,
	whatsapp_account: str | None = None,
	whatsapp_template: str | None = None,
	schedules: Any = None,
) -> dict:
	"""Update a campaign that has not already created a bulk message."""
	doc = frappe.get_doc("UTM Campaign", name)
	frappe.has_permission("UTM Campaign", "write", doc=doc, throw=True)
	if _campaign_has_sent(doc.name):
		frappe.throw(_("This campaign already sent a bulk message and cannot be edited."))
	account = _account_or_throw(whatsapp_account)
	template = _template_or_throw(whatsapp_template)
	new_name = (campaign_name or "").strip() or doc.name
	if new_name != doc.name:
		if frappe.db.exists("UTM Campaign", new_name):
			frappe.throw(_("A campaign named {0} already exists.").format(new_name))
		from frappe.model.rename_doc import rename_doc

		rename_doc("UTM Campaign", doc.name, new_name, show_alert=False)
		doc = frappe.get_doc("UTM Campaign", new_name)
		doc.slug = _unique_slug(new_name, ignore=new_name)
	doc.campaign_description = (campaign_description or "").strip()
	doc.whatsapp_account = account
	_apply_campaign_plan(doc, schedules=schedules, whatsapp_template=template)
	doc.save()
	return get_campaign(doc.name)


def delete_campaign(name: str) -> dict:
	"""Remove a campaign that has not sent a bulk message."""
	doc = frappe.get_doc("UTM Campaign", name)
	frappe.has_permission("UTM Campaign", "delete", doc=doc, throw=True)
	if _campaign_has_sent(doc.name):
		frappe.throw(_("This campaign already sent a bulk message and cannot be deleted."))
	frappe.delete_doc("UTM Campaign", doc.name, ignore_permissions=True)
	return {"name": name, "deleted": True}


def _campaign_has_sent(name: str) -> bool:
	if not frappe.db.exists("DocType", "WA Bulk Message"):
		return False
	return bool(frappe.db.exists("WA Bulk Message", {"campaign": name, "docstatus": 1}))


def _campaign_template(doc) -> str | None:
	"""Template from the first schedule row. Older docs may still carry it in memory."""
	for row in doc.get("whatsapp_schedules") or []:
		template = row.get("whatsapp_template") if isinstance(row, dict) else getattr(row, "whatsapp_template", None)
		if template:
			return template
	return doc.get("whatsapp_template") or doc.get("template")


def _schedule_templates(names: list[str]) -> dict[str, str]:
	if not names or not frappe.db.exists("DocType", "WA Campaign Schedule"):
		return {}
	rows = frappe.get_all(
		"WA Campaign Schedule",
		filters={"parent": ["in", names], "parenttype": "UTM Campaign"},
		fields=["parent", "whatsapp_template", "idx"],
		order_by="idx asc",
		limit_page_length=max(len(names) * 5, 1),
	)
	if not isinstance(rows, list):
		return {}
	found: dict[str, str] = {}
	for row in rows:
		parent = row.get("parent")
		template = row.get("whatsapp_template")
		if parent and template and parent not in found:
			found[parent] = template
	return found


def _recipient_rows(doc) -> list:
	"""In-memory child rows, or the phones on the linked recipient list."""
	rows = doc.get("whatsapp_recipients") or doc.get("recipients")
	if rows:
		return rows
	list_name = doc.get("whatsapp_recipient_list")
	if not list_name or not frappe.db.exists("WA Recipient List", list_name):
		return []
	people = frappe.get_all(
		"WA Recipient",
		filters={"parent": list_name, "parenttype": "WA Recipient List"},
		fields=["mobile_number", "recipient_name", "recipient_data"],
		limit_page_length=500,
	)
	if not isinstance(people, list):
		return []
	loaded = []
	for person in people:
		loaded.append(
			frappe._dict(
				phone_number=person.get("mobile_number"),
				profile=person.get("recipient_name"),
				status="Pending",
				variables_json=person.get("recipient_data"),
				message=None,
				error_message=None,
			)
		)
	return loaded


def _parse_schedules(raw: Any) -> list[dict] | None:
	if raw is None:
		return None
	if isinstance(raw, str):
		text = raw.strip()
		if not text:
			return []
		raw = json.loads(text)
	if not isinstance(raw, (list, tuple)):
		return []
	return [row for row in raw if isinstance(row, dict)]


def _apply_schedules(doc, schedules: list[dict]) -> None:
	doc.set("whatsapp_schedules", [])
	for row in schedules:
		template = (row.get("whatsapp_template") or row.get("template") or "").strip()
		if not template:
			continue
		doc.append(
			"whatsapp_schedules",
			{
				"whatsapp_template": template,
				"send_after_days": int(row.get("send_after_days") or 0),
				"recipient_list": row.get("recipient_list"),
				"variable_type": row.get("variable_type") or "Common",
				"template_variables": row.get("template_variables"),
			},
		)


def _apply_campaign_plan(doc, schedules: Any, whatsapp_template: str | None) -> None:
	"""Write the template schedule. Audience and dates belong to WhatsApp Campaign."""
	parsed = _parse_schedules(schedules)
	if parsed is not None:
		_apply_schedules(doc, parsed)
	elif whatsapp_template:
		_apply_template(doc, whatsapp_template)


def _apply_template(doc, template: str | None) -> None:
	if not template:
		return
	rows = list(doc.get("whatsapp_schedules") or [])
	if rows:
		first = rows[0]
		if isinstance(first, dict):
			first["whatsapp_template"] = template
		else:
			first.whatsapp_template = template
		return
	doc.append(
		"whatsapp_schedules",
		{
			"whatsapp_template": template,
			"send_after_days": 0,
		},
	)


