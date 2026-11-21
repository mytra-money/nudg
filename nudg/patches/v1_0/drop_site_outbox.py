"""Remove the client-site queue DocType. Pending copies live on WA Message."""

from __future__ import annotations

import frappe


def execute():
	if frappe.db.exists("DocType", "WA Site Outbox"):
		frappe.delete_doc("DocType", "WA Site Outbox", force=True, ignore_permissions=True)
