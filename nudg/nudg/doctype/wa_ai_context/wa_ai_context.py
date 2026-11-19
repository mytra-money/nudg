# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WAAIContext(Document):
	def validate(self):
		if not self.whatsapp_account:
			frappe.throw(_("Select the WhatsApp account this context belongs to."))
