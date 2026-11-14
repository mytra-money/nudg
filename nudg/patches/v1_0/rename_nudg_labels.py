"""Rename the all-caps NUDG records to Nudg before DocType sync.

MariaDB's default collation treats "NUDG" and "Nudg" as the same row, so
exists() cannot see the change. A standard Module Def also refuses
rename_doc. The DocType goes through rename_doc (via a temporary name,
because a case-only rename collides). The module and profile names are a
case change on the same row.
"""

import frappe


def execute():
	_rename_doctype("NUDG Conversation", "Nudg Conversation")
	_recase("Module Def", "NUDG", "Nudg")
	_recase("Module Profile", "NUDG Manager", "Nudg Manager")
	_recase("Module Profile", "NUDG Agent", "Nudg Agent")
	_recase_column("DocType", "module", "NUDG", "Nudg")
	_recase_column("Block Module", "module", "NUDG", "Nudg")
	_recase_column("User", "module_profile", "NUDG Manager", "Nudg Manager")
	_recase_column("User", "module_profile", "NUDG Agent", "Nudg Agent")


def _rename_doctype(old, new):
	stored = frappe.db.get_value("DocType", old, "name")
	if stored != old:
		return
	temp = f"{new} Rename"
	frappe.rename_doc("DocType", old, temp, force=True)
	frappe.rename_doc("DocType", temp, new, force=True)


def _recase(doctype, old, new):
	stored = frappe.db.get_value(doctype, old, "name")
	if stored != old:
		return
	frappe.db.sql(f"update `tab{doctype}` set name=%s where name=%s", (new, old))


def _recase_column(doctype, field, old, new):
	if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, field):
		return
	frappe.db.sql(f"update `tab{doctype}` set `{field}`=%s where `{field}`=%s", (new, old))
