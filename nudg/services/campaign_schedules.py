# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Campaign schedules that create bulk WhatsApp messages.

This follows ERPNext Email Campaign timing: a start date plus "send after
days". The row stores a WhatsApp template instead of an email template, and
the send creates one WA Bulk Message instead of an Email Campaign list.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, getdate, today



def schedule_is_due(start_date, send_after_days, on_date=None, already_sent: bool = False) -> bool:
	"""True on the send day, and on later days if that send was missed."""
	if already_sent or start_date in (None, ""):
		return False
	due = add_days(getdate(start_date), int(send_after_days or 0))
	return getdate(on_date or today()) >= getdate(due)


def send_due_campaign_schedules():
	"""Daily job. Each due schedule row becomes one submitted bulk message."""
	if not frappe.db.exists("DocType", "WA Campaign Schedule"):
		return []
	if not frappe.db.has_column("UTM Campaign", "whatsapp_start_date"):
		return []

	parents = frappe.db.sql(
		"""
		select distinct parent
		from `tabWA Campaign Schedule`
		where parenttype = 'UTM Campaign' and ifnull(bulk_message, '') = ''
		"""
	)
	names = [row[0] for row in parents]
	created = []
	for name in names:
		try:
			created.extend(_send_campaign(name))
		except Exception:
			frappe.log_error(title=f"WhatsApp campaign schedule failed: {name}")
	return created


def _send_campaign(name: str) -> list[str]:
	campaign = frappe.get_doc("UTM Campaign", name)
	rows = campaign.get("whatsapp_schedules") or []
	if not rows:
		return []
	start = campaign.get("whatsapp_start_date") or getdate(campaign.creation)
	created = []
	for row in rows:
		if row.bulk_message or not row.whatsapp_template:
			continue
		if not schedule_is_due(start, row.send_after_days, already_sent=False):
			continue
		bulk_name = create_bulk_from_schedule(campaign, row)
		if not bulk_name:
			continue
		frappe.db.set_value("WA Campaign Schedule", row.name, {"bulk_message": bulk_name, "sent_on": today()})
		row.bulk_message = bulk_name
		created.append(bulk_name)
	_sync_status(campaign)
	return created


def create_bulk_from_schedule(campaign, row) -> str | None:
	"""Build and submit the bulk message for one schedule row."""
	account = row.whatsapp_account or campaign.get("whatsapp_account")
	recipient_list = row.recipient_list or campaign.get("whatsapp_recipient_list")
	if not account or not row.whatsapp_template:
		frappe.log_error(title=f"Campaign schedule {campaign.name} needs an account and a template")
		return None

	payload = {
		"doctype": "WA Bulk Message",
		"title": f"{campaign.name} day {int(row.send_after_days or 0)}",
		"whatsapp_account": account,
		"use_template": 1,
		"template": row.whatsapp_template,
		"variable_type": row.variable_type or "Common",
		"template_variables": row.template_variables,
		"campaign": campaign.name,
		"schedule_row": row.name,
		"recipient_type": "Recipient List" if recipient_list else "Individual",
		"recipient_list": recipient_list,
	}
	doc = frappe.get_doc(payload)
	if doc.recipient_type == "Individual" and not doc.recipients:
		frappe.log_error(title=f"Campaign schedule {campaign.name} has no recipients")
		return None
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def _sync_status(campaign):
	rows = campaign.get("whatsapp_schedules") or []
	if not rows:
		return
	start = getdate(campaign.get("whatsapp_start_date") or campaign.creation)
	end = add_days(start, max(int(row.send_after_days or 0) for row in rows))
	status = campaign.get("whatsapp_status") or "Draft"
	if status in ("Cancelled", "Running"):
		return
	if all(row.bulk_message for row in rows) and getdate(today()) > end:
		new_status = "Completed"
	elif getdate(today()) < start:
		new_status = "Scheduled"
	else:
		new_status = "In Progress"
	if status != new_status:
		frappe.db.set_value("UTM Campaign", campaign.name, "whatsapp_status", new_status, update_modified=False)
