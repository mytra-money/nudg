# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""WhatsApp Campaign sends.

This follows Email Campaign. The campaign schedule holds a WhatsApp template
and a send-after delay. The WhatsApp Campaign holds the audience, a start
date, and a trigger time. The end date is the start date plus the longest
delay. A schedule row sends on that exact day, once the trigger time has passed.
"""

from __future__ import annotations

import datetime
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime, today


def schedule_is_due(start_date, send_after_days, on_date=None, already_sent: bool = False) -> bool:
	"""True on the send day, and on later days if that send was missed."""
	if already_sent or start_date in (None, ""):
		return False
	due = add_days(getdate(start_date), int(send_after_days or 0))
	return getdate(on_date or today()) >= getdate(due)


def end_date_for(start_date, send_after_days) -> datetime.date | None:
	"""Same rule as Email Campaign: start date plus the longest send-after."""
	if start_date in (None, "") or not send_after_days:
		return None
	longest = max(int(days or 0) for days in send_after_days)
	return add_days(getdate(start_date), longest)


def _status_for(doc, on_date) -> str:
	"""Scheduled, In Progress, or Completed from the dates, matching Email Campaign."""
	if getattr(doc, "status", None) == "Cancelled":
		return "Cancelled"
	start = getdate(doc.start_date) if doc.start_date else getdate(on_date)
	end = getdate(doc.end_date) if doc.end_date else start
	on = getdate(on_date)
	if on < start:
		return "Scheduled"
	if on <= end:
		return "In Progress"
	return "Completed"


def schedule_sends_on(start_date, send_after_days, on_date) -> bool:
	"""True only on the calendar day Email Campaign would send this row."""
	if start_date in (None, "") or on_date in (None, ""):
		return False
	due = add_days(getdate(start_date), int(send_after_days or 0))
	return getdate(on_date) == getdate(due)


def trigger_time_reached(trigger_time, at=None) -> bool:
	"""True once the clock is at or past this client's trigger time."""
	wanted = _as_time(trigger_time)
	if wanted is None:
		return False
	moment = at if at is not None else datetime.datetime.now()
	if isinstance(moment, datetime.datetime):
		current = moment.time().replace(microsecond=0)
	else:
		current = _as_time(moment)
	return current is not None and current >= wanted


def _as_time(value) -> datetime.time | None:
	if value is None or value == "":
		return None
	if isinstance(value, datetime.time):
		return value.replace(microsecond=0)
	if isinstance(value, datetime.datetime):
		return value.time().replace(microsecond=0)
	if isinstance(value, datetime.timedelta):
		total = int(value.total_seconds()) % 86400
		return datetime.time(total // 3600, (total % 3600) // 60, total % 60)
	text = str(value).strip()
	for fmt in ("%H:%M:%S", "%H:%M"):
		try:
			return datetime.datetime.strptime(text, fmt).time()
		except ValueError:
			continue
	return None


def send_due_campaign_schedules():
	"""Send rows whose day is today and whose client trigger time has passed."""
	if not frappe.db.exists("DocType", "WA Campaign"):
		return []
	names = frappe.get_all(
		"WA Campaign",
		filters={"status": ["not in", ["Cancelled", "Completed"]], "start_date": ["<=", today()]},
		pluck="name",
	)
	if not isinstance(names, list):
		return []
	created = []
	for name in names:
		try:
			created.extend(send_whatsapp_campaign(name))
		except Exception:
			frappe.log_error(title=f"WhatsApp campaign schedule failed: {name}")
	return created


def send_whatsapp_campaign(name: str, on_date=None, at=None) -> list[str]:
	"""Create the bulk message for a schedule row on its exact send day."""
	doc = frappe.get_doc("WA Campaign", name)
	if doc.status == "Cancelled":
		return []
	on = getdate(on_date or today())
	status = _status_for(doc, on)
	if status != doc.status:
		doc.db_set("status", status, update_modified=False)
		doc.status = status
	if status == "Completed":
		return []
	moment = at or now_datetime()
	if not trigger_time_reached(doc.trigger_time, moment):
		return []
	if _is_template_schedule(doc):
		return _send_template_schedule(doc, on)
	if not doc.campaign or not frappe.db.exists("UTM Campaign", doc.campaign):
		frappe.log_error(title=f"WhatsApp Campaign {doc.name} needs a campaign")
		return []
	campaign = frappe.get_doc("UTM Campaign", doc.campaign)
	created = []
	for row in campaign.get("whatsapp_schedules") or []:
		if not row.whatsapp_template or not row.name:
			continue
		if not schedule_sends_on(doc.start_date, row.send_after_days, on):
			continue
		bulk_name = _send_schedule_once(doc.name, campaign, row, on)
		if bulk_name:
			created.append(bulk_name)
	return created


def should_create_bulk(existing_bulk: str | None) -> bool:
	"""One schedule step sends once. A bulk message already stored for it blocks another."""
	return not existing_bulk


def _send_schedule_once(campaign_name: str, utm, row, on) -> str | None:
	"""Create one bulk message for this step, even if the scheduler starts twice.

	The minute job can overlap itself. The lock is held until the bulk message
	commits, so the next run sees it and does not send again.
	"""
	from nudg.services.automation import _acquire_db_lock, _hold_lock_until_commit, _lock_name

	lock = _lock_name("wa-camp", f"{campaign_name}:{row.name}")
	acquired = _acquire_db_lock(lock)
	if not acquired:
		return None
	try:
		existing = _existing_schedule_bulk(campaign_name, row.name)
		doc = frappe.get_doc("WA Campaign", campaign_name)
		if not should_create_bulk(existing):
			_remember_dispatch(doc, row, existing, on)
			return None
		bulk_name = create_bulk_from_whatsapp_campaign(doc, utm, row)
		if not bulk_name:
			return None
		_remember_dispatch(doc, row, bulk_name, on)
		return bulk_name
	finally:
		_hold_lock_until_commit(lock)


def _existing_schedule_bulk(campaign_name: str, schedule_row: str) -> str | None:
	if not schedule_row or not frappe.db.exists("DocType", "WA Bulk Message"):
		return None
	name = frappe.db.get_value(
		"WA Bulk Message",
		{
			"whatsapp_campaign": campaign_name,
			"schedule_row": schedule_row,
			"docstatus": ["!=", 2],
		},
		"name",
	)
	return name or None


def _remember_dispatch(doc, row, bulk_name: str | None, on) -> None:
	"""Point the campaign at the bulk message that already went out. Do not send again."""
	if not bulk_name:
		return
	for existing in doc.dispatches or []:
		if _value(existing, "schedule_row") == row.name and _value(existing, "bulk_message"):
			return
	doc.append(
		"dispatches",
		{
			"schedule_row": row.name,
			"send_after_days": int(row.send_after_days or 0),
			"whatsapp_template": row.whatsapp_template,
			"bulk_message": bulk_name,
			"sent_on": on,
		},
	)
	doc.save(ignore_permissions=True)


def recipient_receives_campaign(unsubscribed, consent_ok: bool = True) -> bool:
	"""A row is sent only when it is still subscribed and consent allows it."""
	if unsubscribed in (1, True, "1"):
		return False
	return bool(consent_ok)


def _is_template_schedule(doc) -> bool:
	return (getattr(doc, "schedule_source", None) or "Campaign") == "Template"


def _send_template_schedule(doc, on) -> list[str]:
	"""One WhatsApp template sends once, on the start date."""
	if not doc.whatsapp_template:
		frappe.log_error(title=f"WhatsApp Campaign {doc.name} needs a template")
		return []
	if not schedule_sends_on(doc.start_date, 0, on):
		return []
	row = frappe._dict(
		name="template",
		whatsapp_template=doc.whatsapp_template,
		send_after_days=0,
		variable_type="Common",
		template_variables="",
	)
	bulk_name = _send_schedule_once(doc.name, None, row, on)
	return [bulk_name] if bulk_name else []


def create_bulk_from_whatsapp_campaign(wa_campaign, campaign, row) -> str | None:
	"""Build and submit the bulk message for one schedule row and one audience."""
	account = campaign.get("whatsapp_account") if campaign else None
	account = account or getattr(wa_campaign, "whatsapp_account", None)
	if not account or not row.whatsapp_template:
		frappe.log_error(title=f"WhatsApp Campaign {wa_campaign.name} needs an account and a template")
		return None
	from nudg.services.campaigns import check_recipient_consent

	recipients = []
	for person in wa_campaign.recipients or []:
		phone = _value(person, "mobile_number")
		if not phone:
			continue
		if not recipient_receives_campaign(_value(person, "unsubscribed"), check_recipient_consent(phone_number=phone)):
			continue
		recipients.append(
			{
				"mobile_number": phone,
				"recipient_name": _value(person, "recipient_name"),
				"recipient_data": _value(person, "recipient_data"),
				"unsubscribed": 0,
			}
		)
	if not recipients:
		return None
	payload = {
		"doctype": "WA Bulk Message",
		"title": _bulk_title(campaign, row),
		"whatsapp_account": account,
		"use_template": 1,
		"template": row.whatsapp_template,
		"variable_type": row.variable_type or "Common",
		"template_variables": row.template_variables,
		"whatsapp_campaign": wa_campaign.name,
		"schedule_row": row.name,
		"recipient_type": "Individual",
		"recipients": recipients,
	}
	if campaign:
		payload["campaign"] = campaign.name
	doc = frappe.get_doc(payload)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def list_whatsapp_campaigns(account: str | None = None) -> list[dict]:
	"""Broadcasts the marketing screen lists. Each one is a WA Campaign."""
	if not frappe.db.exists("DocType", "WA Campaign"):
		return []
	frappe.has_permission("WA Campaign", "read", throw=True)
	filters = {}
	if account:
		filters["whatsapp_account"] = account
	names = frappe.get_list(
		"WA Campaign",
		filters=filters,
		pluck="name",
		order_by="modified desc",
		limit_page_length=50,
	)
	if not isinstance(names, list):
		return []
	return [present(frappe.get_doc("WA Campaign", name)) for name in names]


def get_whatsapp_campaign(name: str) -> dict:
	doc = frappe.get_doc("WA Campaign", name)
	frappe.has_permission("WA Campaign", "read", doc=doc, throw=True)
	return present(doc)


def list_recipient_profiles(account: str | None = None) -> list[dict]:
	"""Profiles the marketing form can attach to a WhatsApp Campaign."""
	if not frappe.db.exists("DocType", "WA Profile"):
		return []
	frappe.has_permission("WA Profile", "read", throw=True)
	filters = {}
	if account:
		filters["whatsapp_account"] = account
	rows = frappe.get_list(
		"WA Profile",
		filters=filters,
		fields=["name", "profile_name", "phone_number", "whatsapp_account"],
		order_by="modified desc",
		limit_page_length=100,
	)
	return rows if isinstance(rows, list) else []


def schedule_whatsapp_campaign(
	campaign: str | None = None,
	recipient_type: str | None = None,
	recipient: str | None = None,
	start_date: str | None = None,
	trigger_time: str | None = None,
	stop_on_reply: int | str | bool | None = 0,
	schedule_for: str | None = None,
	whatsapp_template: str | None = None,
	whatsapp_account: str | None = None,
) -> dict:
	"""Attach an audience and a send time to a campaign or one WhatsApp template."""
	frappe.has_permission("WA Campaign", "create", throw=True)
	source = _schedule_source(schedule_for)
	payload = {
		"doctype": "WA Campaign",
		"schedule_source": source,
		"recipient_type": recipient_type,
		"recipient": recipient,
		"start_date": _date_or_none(start_date),
		"trigger_time": (trigger_time or "").strip() or None,
		"stop_on_reply": _stop_on_reply(stop_on_reply),
	}
	if source == "Template":
		template = (whatsapp_template or "").strip()
		if not template or not frappe.db.exists("WA Template", template):
			frappe.throw(_("Select a WhatsApp template."))
		payload["whatsapp_template"] = template
		account = (whatsapp_account or "").strip() or frappe.db.get_value("WA Template", template, "whatsapp_account")
		if account:
			payload["whatsapp_account"] = account
	else:
		campaign_name = (campaign or "").strip()
		if not campaign_name or not frappe.db.exists("UTM Campaign", campaign_name):
			frappe.throw(_("Select a campaign."))
		payload["campaign"] = campaign_name
	doc = frappe.get_doc(payload)
	doc.insert()
	return present(doc)


def update_whatsapp_schedule(
	name: str,
	campaign: str | None = None,
	recipient_type: str | None = None,
	recipient: str | None = None,
	start_date: str | None = None,
	trigger_time: str | None = None,
	stop_on_reply: int | str | bool | None = None,
	schedule_for: str | None = None,
	whatsapp_template: str | None = None,
	whatsapp_account: str | None = None,
) -> dict:
	"""Change the audience or the clock on a WhatsApp Campaign that has not sent."""
	doc = frappe.get_doc("WA Campaign", name)
	frappe.has_permission("WA Campaign", "write", doc=doc, throw=True)
	if any(row.bulk_message for row in (doc.dispatches or [])):
		frappe.throw(_("This schedule already created a bulk message and cannot be edited."))
	source = _schedule_source(schedule_for or getattr(doc, "schedule_source", None))
	doc.schedule_source = source
	if source == "Template":
		template = (whatsapp_template or doc.whatsapp_template or "").strip()
		if not template or not frappe.db.exists("WA Template", template):
			frappe.throw(_("Select a WhatsApp template."))
		doc.whatsapp_template = template
		doc.campaign = None
		account = (whatsapp_account or "").strip() or frappe.db.get_value("WA Template", template, "whatsapp_account")
		if account:
			doc.whatsapp_account = account
	else:
		campaign_name = (campaign or doc.campaign or "").strip()
		if not campaign_name or not frappe.db.exists("UTM Campaign", campaign_name):
			frappe.throw(_("Select a campaign."))
		doc.campaign = campaign_name
		doc.whatsapp_template = None
	doc.recipient_type = recipient_type
	doc.recipient = recipient
	doc.start_date = _date_or_none(start_date)
	doc.trigger_time = (trigger_time or "").strip() or None
	if stop_on_reply is not None:
		doc.stop_on_reply = _stop_on_reply(stop_on_reply)
	doc.save()
	return present(doc)


def list_bulk_results(account: str | None = None) -> list[dict]:
	"""Submitted and draft bulk messages for the marketing results tab."""
	if not frappe.db.exists("DocType", "WA Bulk Message"):
		return []
	frappe.has_permission("WA Bulk Message", "read", throw=True)
	filters = {}
	if account:
		filters["whatsapp_account"] = account
	rows = frappe.get_list(
		"WA Bulk Message",
		filters=filters,
		fields=[
			"name",
			"title",
			"status",
			"sent_count",
			"failed_count",
			"recipient_count",
			"campaign",
			"whatsapp_campaign",
			"template",
			"whatsapp_account",
			"modified",
			"docstatus",
		],
		order_by="modified desc",
		limit_page_length=50,
	)
	if not isinstance(rows, list):
		return []
	from nudg.services.display_titles import account_titles, bulk_display_title, template_titles

	templates = template_titles([row.get("template") for row in rows])
	accounts = account_titles([row.get("whatsapp_account") for row in rows])
	presented = []
	for row in rows:
		template_label = templates.get(row.get("template")) or ""
		campaign_label = row.get("campaign") or ""
		item = dict(row)
		item["template_label"] = template_label
		item["campaign_label"] = campaign_label
		item["account_label"] = accounts.get(row.get("whatsapp_account")) or ""
		item["title"] = bulk_display_title(row.get("title"), campaign_label, template_label)
		presented.append(item)
	return presented


def _bulk_title(campaign, row) -> str:
	from nudg.services.display_titles import bulk_display_title, template_titles

	template = _value(row, "whatsapp_template")
	label = template_titles([template]).get(template) if template else ""
	day = int(_value(row, "send_after_days") or 0)
	title = bulk_display_title("", getattr(campaign, "name", None) if campaign else "", label)
	if day:
		return f"{title} · day {day}"
	return title


def _schedule_view(row, titles: dict) -> dict:
	data = row.as_dict() if hasattr(row, "as_dict") else dict(row)
	template = data.get("whatsapp_template")
	data["template_label"] = titles.get(template) or ""
	return data


def create_whatsapp_campaign(
	name: str,
	campaign_description: str | None = None,
	whatsapp_account: str | None = None,
	recipient_type: str | None = None,
	recipient: str | None = None,
	start_date: str | None = None,
	trigger_time: str | None = None,
	stop_on_reply: int | str | bool | None = 0,
	schedules: Any = None,
) -> dict:
	"""Create the template campaign and the WhatsApp Campaign that sends it."""
	from nudg.services.campaigns import create_campaign

	frappe.has_permission("WA Campaign", "create", throw=True)
	campaign = create_campaign(
		name,
		campaign_description,
		whatsapp_account,
		schedules=schedules,
	)
	doc = frappe.get_doc(
		{
			"doctype": "WA Campaign",
			"campaign": campaign["name"],
			"recipient_type": recipient_type,
			"recipient": recipient,
			"start_date": _date_or_none(start_date),
			"trigger_time": (trigger_time or "").strip() or None,
			"stop_on_reply": _stop_on_reply(stop_on_reply),
		}
	)
	doc.insert()
	return present(doc)


def update_whatsapp_campaign(
	name: str,
	campaign_name: str | None = None,
	campaign_description: str | None = None,
	whatsapp_account: str | None = None,
	recipient_type: str | None = None,
	recipient: str | None = None,
	start_date: str | None = None,
	trigger_time: str | None = None,
	stop_on_reply: int | str | bool | None = None,
	schedules: Any = None,
) -> dict:
	from nudg.services.campaigns import update_campaign

	doc = frappe.get_doc("WA Campaign", name)
	frappe.has_permission("WA Campaign", "write", doc=doc, throw=True)
	if any(row.bulk_message for row in (doc.dispatches or [])):
		frappe.throw(_("This broadcast already created a bulk message and cannot be edited."))
	updated = update_campaign(
		doc.campaign,
		campaign_name,
		campaign_description,
		whatsapp_account,
		schedules=schedules,
	)
	doc.campaign = updated["name"]
	doc.recipient_type = recipient_type
	doc.recipient = recipient
	doc.start_date = _date_or_none(start_date)
	doc.trigger_time = (trigger_time or "").strip() or None
	if stop_on_reply is not None:
		doc.stop_on_reply = _stop_on_reply(stop_on_reply)
	doc.save()
	return present(doc)


def delete_whatsapp_campaign(name: str) -> dict:
	"""Remove one schedule. The campaign and its template stay."""
	doc = frappe.get_doc("WA Campaign", name)
	frappe.has_permission("WA Campaign", "delete", doc=doc, throw=True)
	if any(row.bulk_message for row in (doc.dispatches or [])):
		frappe.throw(_("This schedule already created a bulk message and cannot be deleted."))
	frappe.delete_doc("WA Campaign", doc.name, ignore_permissions=True)
	return {"name": name, "deleted": True}


def present(doc) -> dict:
	"""Shape the marketing screen reads."""
	source = "Template" if _is_template_schedule(doc) else "Campaign"
	campaign = None
	if source == "Campaign" and doc.campaign and frappe.db.exists("UTM Campaign", doc.campaign):
		campaign = frappe.get_doc("UTM Campaign", doc.campaign)
	schedules = (campaign.get("whatsapp_schedules") or []) if campaign else []
	first = schedules[0] if schedules else None
	template = doc.whatsapp_template if source == "Template" else _value(first, "whatsapp_template")
	from nudg.services.display_titles import account_titles, audience_title, template_titles

	template_names = [name for name in (_value(row, "whatsapp_template") for row in schedules) if name]
	if template:
		template_names.append(template)
	titles = template_titles(template_names)
	account = doc.whatsapp_account or (campaign.get("whatsapp_account") if campaign else None)
	if source == "Template" and template:
		schedules_view = [
			{
				"whatsapp_template": template,
				"template_label": titles.get(template) or "",
				"send_after_days": 0,
				"variable_type": "Common",
			}
		]
		campaign_name = titles.get(template) or ""
	else:
		schedules_view = [_schedule_view(row, titles) for row in schedules]
		campaign_name = doc.campaign
	sent, failed = _bulk_counts(doc)
	recipients = []
	for row in doc.recipients or []:
		recipients.append(
			{
				"profile": _value(row, "recipient_name") or _value(row, "mobile_number"),
				"phone_number": _value(row, "mobile_number"),
				"recipient_name": _value(row, "recipient_name"),
				"unsubscribed": 1 if _value(row, "unsubscribed") else 0,
			}
		)
	return {
		"name": doc.name,
		"schedule_source": source,
		"campaign": doc.campaign if source == "Campaign" else "",
		"campaign_name": campaign_name,
		"description": campaign.get("campaign_description") if campaign else "",
		"campaign_description": campaign.get("campaign_description") if campaign else "",
		"whatsapp_account": account,
		"account_label": account_titles([account]).get(account) if account else "",
		"whatsapp_channel": account,
		"recipient_type": doc.recipient_type,
		"recipient": doc.recipient,
		"recipient_label": audience_title(doc.recipient_type, doc.recipient),
		"start_date": doc.start_date,
		"end_date": doc.end_date,
		"trigger_time": doc.trigger_time,
		"stop_on_reply": 1 if _value(doc, "stop_on_reply") else 0,
		"status": doc.status or "Draft",
		"template": template,
		"template_label": titles.get(template) or "",
		"whatsapp_template": template,
		"send_after_days": int(_value(first, "send_after_days") or 0),
		"whatsapp_schedules": schedules_view,
		"recipients": recipients,
		"sent_count": sent,
		"failed_count": failed,
		"can_edit": not any(_value(row, "bulk_message") for row in (doc.dispatches or [])),
		"modified": doc.modified,
	}


def _bulk_counts(doc) -> tuple[int, int]:
	sent = 0
	failed = 0
	if not frappe.db.exists("DocType", "WA Bulk Message"):
		return sent, failed
	for row in doc.dispatches or []:
		bulk_name = _value(row, "bulk_message")
		if not bulk_name:
			continue
		counts = frappe.db.get_value("WA Bulk Message", bulk_name, ["sent_count", "failed_count"], as_dict=True) or {}
		sent += int(counts.get("sent_count") or 0)
		failed += int(counts.get("failed_count") or 0)
	return sent, failed


def _value(row, field):
	if row is None:
		return None
	if isinstance(row, dict):
		return row.get(field)
	return getattr(row, field, None)


def _date_or_none(value: str | None):
	text = (value or "").strip()
	return text[:10] if text else None


def _stop_on_reply(value) -> int:
	return 1 if str(value).strip().lower() in {"1", "true", "yes"} else 0


def _schedule_source(value: str | None) -> str:
	return "Template" if str(value or "").strip().lower() == "template" else "Campaign"
