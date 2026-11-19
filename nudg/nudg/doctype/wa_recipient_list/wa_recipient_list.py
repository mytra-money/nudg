# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document

from nudg.services.bulk import import_rows


class WARecipientList(Document):
	def validate(self):
		if not self.is_new() and not self.recipients:
			frappe.throw(_("Add at least one recipient."))

	def import_list_from_doctype(self, doctype, mobile_field, name_field=None, filters=None, limit=None, data_fields=None):
		"""Replace this list with rows imported from another DocType."""
		self.doctype_to_import = doctype
		self.mobile_field = mobile_field
		self.name_field = name_field
		if filters is not None:
			self.import_filters = filters if isinstance(filters, str) else json.dumps(filters)
		if data_fields is not None:
			self.data_fields = data_fields if isinstance(data_fields, str) else json.dumps(data_fields)
		if limit:
			self.import_limit = limit
		self.recipients = []
		for row in import_rows(doctype, mobile_field, name_field, filters, limit, data_fields):
			self.append("recipients", row)
		return len(self.recipients)
