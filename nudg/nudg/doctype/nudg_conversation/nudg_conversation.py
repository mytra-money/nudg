# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from nudg.services.assignments import on_conversation_update


class NudgConversation(Document):
	def on_update(self):
		on_conversation_update(self)


# Desk resolves the class from the DocType name. Sites that have not migrated
# still have "NUDG Conversation", which looks up this name.
NudgConversation = NudgConversation
