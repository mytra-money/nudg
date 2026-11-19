"""Turn the site-wide WA Chatbot Single into one document per WhatsApp account.

The old record lived in tabSingles. If it named an account, that account keeps
its settings. A chatbot with no account is dropped, because one setup must not
answer every customer.
"""

import frappe


_FIELDS = (
	"enabled",
	"default_response",
	"business_hours_only",
	"out_of_hours_message",
	"enable_ai",
	"ai_provider",
	"ai_model",
	"ai_max_tokens",
	"ai_temperature",
	"ai_include_history",
	"ai_history_limit",
	"ai_system_prompt",
	"session_timeout_minutes",
	"log_conversations",
)


def _append_children(doc, child_doctype: str, fieldname: str, columns: tuple[str, ...]) -> None:
	if not frappe.db.table_exists(child_doctype):
		return
	rows = frappe.get_all(
		child_doctype,
		filters={"parent": "WA Chatbot", "parenttype": "WA Chatbot", "parentfield": fieldname},
		fields=list(columns),
		order_by="idx asc",
	)
	for row in rows:
		doc.append(fieldname, {column: row.get(column) for column in columns})
	if rows:
		frappe.db.delete(child_doctype, {"parent": "WA Chatbot", "parenttype": "WA Chatbot"})


def execute():
	if not frappe.db.table_exists("WA Chatbot"):
		return
	if not frappe.db.table_exists("Singles"):
		return
	rows = frappe.db.sql(
		"select field, value from `tabSingles` where doctype = 'WA Chatbot'",
		as_dict=True,
	)
	if not rows:
		return
	data = {row.field: row.value for row in rows}
	account = data.get("whatsapp_account")
	if account and frappe.db.exists("WA Account", account) and not frappe.db.exists("WA Chatbot", {"whatsapp_account": account}):
		doc = frappe.new_doc("WA Chatbot")
		doc.whatsapp_account = account
		for field in _FIELDS:
			if data.get(field) not in (None, ""):
				doc.set(field, data[field])
		if doc.enable_ai and not data.get("ai_api_key"):
			doc.enable_ai = 0
		_append_children(doc, "WA Business Hours", "business_hours", ("day", "enabled", "start_time", "end_time"))
		_append_children(doc, "WA Excluded Number", "excluded_numbers", ("phone_number", "reason"))
		if doc.business_hours_only and not doc.business_hours:
			doc.business_hours_only = 0
		doc.insert(ignore_permissions=True)
		secret = data.get("ai_api_key")
		if secret:
			frappe.db.sql("update `tabWA Chatbot` set ai_api_key = %s where name = %s", (secret, doc.name))
	frappe.db.sql("delete from `tabSingles` where doctype = 'WA Chatbot'")
