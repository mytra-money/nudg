# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WAChatbot(Document):
	def validate(self):
		if not self.whatsapp_account:
			frappe.throw(_("Select the WhatsApp account this chatbot answers."))
		if self.enable_ai:
			if not self.ai_provider:
				frappe.throw(_("Select an AI provider when AI is enabled."))
			if not self.get("ai_api_key"):
				frappe.throw(_("Enter an API key when AI is enabled."))
		if self.business_hours_only and not self.business_hours:
			frappe.throw(_("Add business hours for at least one day."))
		if self.ai_temperature not in (None, "") and (float(self.ai_temperature) < 0 or float(self.ai_temperature) > 1):
			frappe.throw(_("AI temperature must be between 0 and 1."))

	@frappe.whitelist()
	def populate_default_business_hours(self):
		"""Weekdays 09:00–18:00, weekend closed."""
		self.business_hours = []
		for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
			weekday = day not in ("Saturday", "Sunday")
			self.append("business_hours", {
				"day": day,
				"enabled": 1 if weekday else 0,
				"start_time": "09:00:00" if weekday else None,
				"end_time": "18:00:00" if weekday else None,
			})
		self.save()
		return {"message": _("Default business hours populated.")}
