# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from nudg.services.assignments import on_conversation_update


class NudgConversation(Document):
	def on_update(self):
		on_conversation_update(self)
