# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class WAChatbotSession(Document):
	def before_save(self):
		if self.status == "Active":
			self.last_activity = now_datetime()

	def add_message(self, direction, message, step_name=None):
		"""Append one turn. Skipped when the chatbot has conversation logging off."""
		try:
			from nudg.services.chatbot import get_settings

			settings = get_settings(self.whatsapp_account)
			if settings and not settings.log_conversations:
				return
		except Exception:
			pass
		self.append("messages", {
			"direction": direction,
			"message": message,
			"timestamp": now_datetime(),
			"step_name": step_name,
		})
