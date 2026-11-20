"""Drop campaign and profile custom fields that schedules replaced.

UTM Campaign keeps whatsapp_schedules and whatsapp_recipient_list. The hidden
single-send columns are not recreated. WA Profile consent lives on status,
not on consent_status or consent_reason.
"""

from __future__ import annotations

import frappe

FIELDS_TO_DROP = {
	"UTM Campaign": (
		"whatsapp_template",
		"whatsapp_scheduled_at",
		"whatsapp_audience_filter",
		"whatsapp_recipients_section",
		"whatsapp_recipients",
	),
	"WA Profile": (
		"consent_status",
		"consent_reason",
	),
}


def execute():
	for dt, fieldnames in FIELDS_TO_DROP.items():
		if not frappe.db.exists("DocType", "Custom Field"):
			break
		for fieldname in fieldnames:
			custom_field_name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname})
			if not custom_field_name:
				continue
			frappe.delete_doc("Custom Field", custom_field_name, force=True, ignore_permissions=True)
		frappe.clear_cache(doctype=dt)
	frappe.clear_cache()
