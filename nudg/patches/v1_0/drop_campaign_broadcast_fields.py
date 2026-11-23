"""Move broadcast audience and dates off UTM Campaign.

Sent, delivered, read, failed, status, start date, and the default recipient
list now live on WA Campaign. That document creates the bulk message.
"""

from __future__ import annotations

import frappe

FIELDS_TO_DROP = (
	"whatsapp_status",
	"whatsapp_col_break",
	"whatsapp_sent_count",
	"whatsapp_delivered_count",
	"whatsapp_read_count",
	"whatsapp_failed_count",
	"whatsapp_start_date",
	"whatsapp_recipient_list",
)


def execute():
	if not frappe.db.exists("DocType", "Custom Field"):
		return
	for fieldname in FIELDS_TO_DROP:
		custom_field_name = frappe.db.get_value("Custom Field", {"dt": "UTM Campaign", "fieldname": fieldname})
		if not custom_field_name:
			continue
		frappe.delete_doc("Custom Field", custom_field_name, force=True, ignore_permissions=True)
	frappe.clear_cache(doctype="UTM Campaign")
