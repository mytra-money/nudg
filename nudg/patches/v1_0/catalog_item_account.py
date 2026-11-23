"""Copy each catalog's WhatsApp account onto its products.

User Permission on WA Account filters a document only when that document
stores the account. Products created before the field existed need a backfill.
"""

import frappe


def execute():
	if not frappe.db.table_exists("WA Catalog") or not frappe.db.table_exists("WA Catalog Item"):
		return
	if not frappe.db.has_column("WA Catalog Item", "whatsapp_account"):
		return
	if not frappe.db.has_column("WA Catalog", "whatsapp_account"):
		return
	frappe.db.sql(
		"""
		UPDATE `tabWA Catalog Item` item
		INNER JOIN `tabWA Catalog` catalog ON catalog.name = item.catalog
		SET item.whatsapp_account = catalog.whatsapp_account
		WHERE IFNULL(item.whatsapp_account, '') != IFNULL(catalog.whatsapp_account, '')
		"""
	)
