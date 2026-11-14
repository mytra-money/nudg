# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Guest endpoint called by an ERPNext Webhook. Chat traffic does not come through here."""

from __future__ import annotations

import frappe

from nudg.integrations.erpnext.service import accept_event


@frappe.whitelist(allow_guest=True, methods=["POST"])
def receive():
	raw = frappe.request.get_data(cache=True, as_text=False) if frappe.request else b""
	if isinstance(raw, str):
		raw = raw.encode("utf-8")
	site = frappe.get_request_header("X-Nudge-Site") if frappe.request else ""
	signature = frappe.get_request_header("X-Frappe-Webhook-Signature") if frappe.request else ""
	auth = frappe.get_request_header("Authorization") if frappe.request else ""
	bearer = ""
	if auth and auth.lower().startswith("bearer "):
		bearer = auth.split(" ", 1)[1].strip()
	return accept_event(raw or b"", site, signature, bearer)
