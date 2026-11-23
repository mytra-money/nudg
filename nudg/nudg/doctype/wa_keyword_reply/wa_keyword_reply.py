# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


class WAKeywordReply(Document):
	def validate(self):
		if not self.whatsapp_account:
			frappe.throw(_("Select the WhatsApp account this reply belongs to."))
		self.validate_keywords()
		self.validate_response()
		self.validate_dates()

	def validate_keywords(self):
		if not (self.keywords or "").strip():
			frappe.throw(_("Enter at least one keyword."))
		if self.match_type == "Regex":
			for keyword in [part.strip() for part in self.keywords.split(",") if part.strip()]:
				try:
					re.compile(keyword)
				except re.error as exc:
					frappe.throw(_("Invalid regex '{0}': {1}").format(keyword, exc))

	def validate_response(self):
		if self.response_type in ("Text", "Unsubscribe", "Subscribe") and not self.response_text:
			frappe.throw(_("Enter the response text."))
		elif self.response_type == "Template" and not self.response_template:
			frappe.throw(_("Select a WhatsApp template."))
		elif self.response_type == "Media":
			if not self.media_type or not self.media_url:
				frappe.throw(_("Select a media type and a file or URL."))
		elif self.response_type == "Flow" and not self.trigger_flow:
			frappe.throw(_("Select the chatbot flow to start."))
		elif self.response_type == "Script" and not self.script:
			frappe.throw(_("Enter a Server Script name or a dotted method path."))

	def validate_dates(self):
		if self.active_from and self.active_until and self.active_from > self.active_until:
			frappe.throw(_("Active From must be before Active Until."))
