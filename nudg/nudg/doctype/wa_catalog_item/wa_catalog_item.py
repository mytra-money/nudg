# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WACatalogItem(Document):
	def has_permission(self, permtype="read", *, debug=False, user=None) -> bool:
		# Permission runs before validate. Copy the catalog account first so a
		# missing client value cannot skip the WhatsApp Account check.
		self._set_whatsapp_account()
		return super().has_permission(permtype, debug=debug, user=user)

	def validate(self):
		self._set_whatsapp_account()
		self._sync_from_erpnext_item()

	def _set_whatsapp_account(self):
		"""Keep the item on the same WhatsApp account as its catalog."""
		catalog = getattr(self, "catalog", None)
		if not catalog or not getattr(frappe.local, "db", None):
			return
		try:
			if not frappe.db.exists("DocType", "WA Catalog"):
				return
			account = frappe.db.get_value("WA Catalog", catalog, "whatsapp_account")
		except Exception:
			return
		self.whatsapp_account = account or None

	def _sync_from_erpnext_item(self):
		"""Sync standard Item properties if erpnext_item/item_code is optionally linked."""
		item_ref = getattr(self, "erpnext_item", None) or getattr(self, "item_code", None)
		if not item_ref or not getattr(frappe.local, "db", None):
			return

		if not frappe.db.exists("DocType", "Item"):
			return

		if frappe.db.exists("Item", item_ref):
			item = frappe.get_doc("Item", item_ref)
			if not self.item_name:
				self.item_name = item.item_name or item.item_code
			if not self.description:
				self.description = item.description
			if not self.image and getattr(item, "image", None):
				self.image = item.image
			if not self.sku:
				self.sku = item.item_code
			if (not self.price or self.price == 0) and frappe.db.exists("DocType", "Item Price"):
				try:
					price_row = frappe.db.get_value(
						"Item Price",
						{"item_code": item_ref, "selling": 1},
						["price_list_rate", "currency"],
						as_dict=True,
					)
					if price_row:
						self.price = price_row.price_list_rate
						if price_row.currency:
							self.currency = price_row.currency
				except Exception:
					pass
