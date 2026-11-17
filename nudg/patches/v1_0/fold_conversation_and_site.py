"""Move Connected Site onto WA Account, and WA Conversation onto WA Profile.

A chat is the profile plus its WA Message rows. Assignment, tags, and the
cached inbox status move onto the profile. Comments and ToDos follow.
An ERPNext connection is one tab on the WhatsApp account. The old DocTypes
are removed after the copy.
"""

from __future__ import annotations

import frappe

_SITE_DOCTYPES = ("Connected Site", "ERPNext Site", "WA ERPNext Site")
_CONVERSATION_DOCTYPES = ("WA Conversation", "Nudg Conversation", "NUDG Conversation")


def execute():
	_ensure_fields()
	for doctype in _SITE_DOCTYPES:
		_fold_sites(doctype)
	for doctype in _CONVERSATION_DOCTYPES:
		_fold_conversations(doctype)


def _ensure_fields():
	if not getattr(frappe.local, "db", None):
		return
	from nudg.install import setup_standard_custom_fields

	setup_standard_custom_fields()


def _fold_sites(doctype: str):
	if not frappe.db.exists("DocType", doctype):
		return
	if not frappe.db.table_exists(doctype):
		_drop_doctype(doctype)
		return
	if frappe.db.exists("DocType", "WA Account") and _has_column("WA Account", "erp_site_name"):
		columns = set(frappe.db.get_table_columns(doctype) or [])
		if "site_url" in columns:
			rows = frappe.get_all(doctype, fields=["name", "modified"], order_by="modified asc")
			for row in rows:
				_copy_site(doctype, row.name)
	_drop_doctype(doctype)


def _copy_site(doctype: str, name: str):
	# Read the table directly. The controller module is already gone.
	row = _row(
		doctype,
		name,
		["name", "site_name", "status", "site_url", "whatsapp_account", "remote_user", "last_error"],
	)
	if not row:
		return
	account_name = row.get("whatsapp_account")
	if not account_name or not frappe.db.exists("WA Account", account_name):
		return
	account = frappe.get_doc("WA Account", account_name)
	account.erp_site_name = row.get("site_name") or row.get("name")
	account.erp_status = row.get("status") or "Pending"
	account.erp_site_url = row.get("site_url")
	account.erp_remote_user = row.get("remote_user")
	account.erp_last_error = row.get("last_error")
	for source, target in (
		("api_key", "erp_api_key"),
		("api_secret", "erp_api_secret"),
		("inbound_secret", "erp_inbound_secret"),
	):
		plain = _password(doctype, name, source)
		if plain:
			account.set(target, plain)
	account.flags.ignore_validate = True
	account.flags.ignore_permissions = True
	account.flags.ignore_mandatory = True
	account.save(ignore_permissions=True)


def _fold_conversations(doctype: str):
	if not frappe.db.exists("DocType", doctype):
		return
	if frappe.db.table_exists(doctype) and frappe.db.exists("DocType", "WA Profile"):
		columns = set(frappe.db.get_table_columns(doctype) or [])
		if "profile" in columns:
			rows = frappe.get_all(doctype, pluck="name")
			for name in rows:
				_copy_conversation(doctype, name)
	if frappe.db.exists("DocType", "Assignment Rule") and frappe.db.has_column("Assignment Rule", "document_type"):
		frappe.db.sql(
			"""update `tabAssignment Rule`
			   set document_type='WA Profile'
			   where document_type=%s""",
			(doctype,),
		)
	_drop_doctype(doctype)


def _copy_conversation(doctype: str, name: str):
	row = _row(
		doctype,
		name,
		[
			"profile",
			"assignee",
			"assignment_status",
			"conversation_status",
			"priority",
			"tags",
			"last_assigned_on",
			"assignment_source",
			"reference_doctype",
			"reference_name",
		],
	)
	if not row:
		return
	profile_name = row.get("profile")
	if not profile_name or not frappe.db.exists("WA Profile", profile_name):
		return
	profile = frappe.get_doc("WA Profile", profile_name)
	for field in (
		"assignee",
		"assignment_status",
		"conversation_status",
		"priority",
		"tags",
		"last_assigned_on",
		"assignment_source",
	):
		value = row.get(field)
		if value not in (None, ""):
			profile.set(field, value)
	link_doctype = row.get("reference_doctype")
	link_name = row.get("reference_name")
	if link_doctype and link_name:
		already = {(link.link_doctype, link.link_name) for link in (profile.get("links") or [])}
		if (link_doctype, link_name) not in already:
			profile.append("links", {"link_doctype": link_doctype, "link_name": link_name})
	profile.flags.ignore_validate = True
	profile.flags.ignore_permissions = True
	profile.flags.ignore_mandatory = True
	profile.save(ignore_permissions=True)
	_retarget("Comment", "reference_doctype", "reference_name", doctype, name, profile_name)
	_retarget("ToDo", "reference_type", "reference_name", doctype, name, profile_name)


def _retarget(doctype: str, type_field: str, name_field: str, old_type: str, old_name: str, profile: str):
	if not frappe.db.table_exists(doctype):
		return
	frappe.db.sql(
		f"""update `tab{doctype}`
		    set `{type_field}`='WA Profile', `{name_field}`=%s
		    where `{type_field}`=%s and `{name_field}`=%s""",
		(profile, old_type, old_name),
	)


def _drop_doctype(name: str):
	if not frappe.db.exists("DocType", name):
		return
	# Mark custom so delete does not import the removed controller module.
	frappe.db.set_value("DocType", name, "custom", 1, update_modified=False)
	controllers = getattr(frappe, "controllers", None)
	if controllers is not None:
		controllers.get(getattr(frappe.local, "site", None), {}).pop(name, None)
	frappe.delete_doc(
		"DocType",
		name,
		force=True,
		ignore_permissions=True,
		ignore_on_trash=True,
		delete_permanently=True,
	)


def _row(doctype: str, name: str, fields: list[str]):
	columns = set(frappe.db.get_table_columns(doctype) or [])
	selected = [field for field in fields if field in columns]
	if not selected:
		return None
	return frappe.db.get_value(doctype, name, selected, as_dict=True)


def _password(doctype: str, name: str, fieldname: str):
	from frappe.utils.password import get_decrypted_password

	try:
		return get_decrypted_password(doctype, name, fieldname, raise_exception=False)
	except Exception:
		return None


def _has_column(doctype: str, fieldname: str) -> bool:
	try:
		return bool(frappe.db.has_column(doctype, fieldname))
	except Exception:
		return False
