# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import secrets

import frappe
from frappe import _
from frappe.model.document import Document

from nudg.integrations.erpnext.safety import SiteURLError, validate_site_url


class ERPNextSite(Document):
	def before_insert(self):
		if not self.inbound_secret:
			self.inbound_secret = secrets.token_urlsafe(32)
		if not self.status:
			self.status = "Pending"

	def validate(self):
		if not self.site_url:
			return
		try:
			allow_http = bool(getattr(frappe.conf, "developer_mode", False))
			self.site_url = validate_site_url(self.site_url, allow_http=allow_http)
		except SiteURLError as exc:
			frappe.throw(_(str(exc)))
