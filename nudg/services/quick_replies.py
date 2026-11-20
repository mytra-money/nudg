"""Quick reply list and usage tracking."""

from __future__ import annotations

import frappe
from frappe import _


def list_quick_replies(
	account: str | None = None,
	status: str | None = "Active",
	start: int | None = 0,
	limit: int | None = None,
) -> list[dict]:
	from nudg.paging import page_limit, page_start

	frappe.has_permission("WA Quick Reply", "read", throw=True)
	filters: dict = {}
	if status:
		filters["status"] = status
	rows = frappe.get_list(
		"WA Quick Reply",
		filters=filters,
		fields=["name", "title", "shortcut", "body", "whatsapp_account", "status", "usage_count", "modified"],
		order_by="modified desc",
		limit_start=page_start(start),
		limit_page_length=page_limit(limit, default=50, maximum=50),
	)
	if account:
		rows = [row for row in rows if not row.whatsapp_account or row.whatsapp_account == account]
	return rows


def use_quick_reply(name: str) -> dict:
	"""Increment usage_count and return the reply body for the composer."""
	if not name:
		frappe.throw(_("Quick Reply is required."))
	doc = frappe.get_doc("WA Quick Reply", name)
	frappe.has_permission("WA Quick Reply", "read", doc=doc, throw=True)
	if doc.status != "Active":
		frappe.throw(_("Quick Reply {0} is not Active.").format(name))
	doc.db_set("usage_count", int(doc.usage_count or 0) + 1, update_modified=False)
	return {
		"name": doc.name,
		"title": doc.title,
		"body": doc.body,
		"shortcut": doc.shortcut,
		"usage_count": int(doc.usage_count or 0) + 1,
	}
