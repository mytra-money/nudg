# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class WASignupSettings(Document):
	def before_validate(self):
		if not self.enabled:
			self.flags.ignore_mandatory = True
