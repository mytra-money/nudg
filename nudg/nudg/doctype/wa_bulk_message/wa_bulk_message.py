# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import get_datetime, now_datetime

from nudg.services.bulk import get_progress, queue_messages, retry_failed, validate_schedule


class WABulkMessage(Document):
	def autoname(self):
		if not self.name or self.name.startswith("new-"):
			self.name = make_autoname("BULK-WA-.YYYY.-.#####")

	def validate(self):
		self.validate_recipients()
		if self.docstatus == 0:
			validate_schedule(self.scheduled_time)

	def validate_recipients(self):
		if self.recipient_type == "Recipient List":
			if not self.recipient_list:
				frappe.throw(_("Select a recipient list."))
			count = frappe.db.count("WA Recipient", {"parent": self.recipient_list, "parenttype": "WA Recipient List"})
			if count == 0 and not self.is_new():
				frappe.throw(_("The selected recipient list is empty."))
			self.recipient_count = count
		else:
			if not self.recipients:
				frappe.throw(_("Add at least one recipient."))
			self.recipient_count = len(self.recipients)

	def before_submit(self):
		if self.use_template and not self.template:
			frappe.throw(_("Select a WhatsApp template."))

	def on_submit(self):
		if self.scheduled_time and get_datetime(self.scheduled_time) > now_datetime():
			self.db_set("status", "Scheduled")
			return
		self.db_set("status", "Queued")
		queue_messages(self)

	def get_progress(self):
		return get_progress(self.name)

	def retry_failed(self):
		count = retry_failed(self)
		frappe.msgprint(_("{0} message(s) requeued.").format(count))
		return count
