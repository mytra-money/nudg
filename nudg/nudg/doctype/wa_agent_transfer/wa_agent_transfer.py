# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class WAAgentTransfer(Document):
	def before_save(self):
		if self.agent and not self.agent_name:
			self.agent_name = frappe.db.get_value("User", self.agent, "full_name")
		if self.has_value_changed("status") and self.status == "Resumed":
			self.resumed_at = now_datetime()
			self.resumed_by = frappe.session.user

	@staticmethod
	def is_transferred(phone_number, whatsapp_account=None):
		filters = {"phone_number": phone_number, "status": "Active"}
		if whatsapp_account:
			filters["whatsapp_account"] = whatsapp_account
		return frappe.db.exists("WA Agent Transfer", filters)

	@staticmethod
	def transfer_to_agent(phone_number, whatsapp_account=None, agent=None, notes=None):
		existing = frappe.db.exists("WA Agent Transfer", {"phone_number": phone_number, "status": "Active"})
		if existing:
			return frappe.get_doc("WA Agent Transfer", existing)
		doc = frappe.get_doc({
			"doctype": "WA Agent Transfer",
			"phone_number": phone_number,
			"whatsapp_account": whatsapp_account,
			"agent": agent,
			"notes": notes,
			"status": "Active",
			"transferred_at": now_datetime(),
		})
		doc.insert(ignore_permissions=True)
		return doc

	@staticmethod
	def resume_chatbot(phone_number, whatsapp_account=None):
		filters = {"phone_number": phone_number, "status": "Active"}
		if whatsapp_account:
			filters["whatsapp_account"] = whatsapp_account
		names = frappe.get_all("WA Agent Transfer", filters=filters, pluck="name")
		if not names:
			return False
		for name in names:
			doc = frappe.get_doc("WA Agent Transfer", name)
			doc.status = "Resumed"
			doc.save(ignore_permissions=True)
		return True
