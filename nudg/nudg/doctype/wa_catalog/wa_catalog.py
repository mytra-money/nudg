# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WACatalog(Document):
	def on_update(self):
		self._sync_item_accounts()

	def _sync_item_accounts(self):
		"""User Permission reads the account on each item, so keep those rows current."""
		if not getattr(frappe.local, "db", None) or not self.name:
			return
		try:
			if not frappe.db.table_exists("WA Catalog Item"):
				return
			if not frappe.db.has_column("WA Catalog Item", "whatsapp_account"):
				return
		except Exception:
			return
		account = self.whatsapp_account or None
		frappe.db.sql(
			"""
			UPDATE `tabWA Catalog Item`
			SET whatsapp_account = %s
			WHERE catalog = %s
			  AND IFNULL(whatsapp_account, '') != IFNULL(%s, '')
			""",
			(account, self.name, account),
		)
