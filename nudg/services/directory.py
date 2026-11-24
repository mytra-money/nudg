# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Contacts and recipient lists for the desk.

Create, edit, and delete follow Role Permission Manager. A role that can
read WA Profile can open contacts. Write, create, and delete are separate
checks on WA Profile and WA Recipient List.
"""

from __future__ import annotations

import json
import re

import frappe
from frappe import _
from frappe.utils import cint

from nudg.utils.phone import normalize_mobile_no

PROFILE_STATUSES = ("Active", "Blocked", "Archived")
PTYPES = ("read", "write", "create", "delete")


def access() -> dict:
	"""Role permissions for the contacts sidebar."""
	return {
		"profile": _flags("WA Profile"),
		"recipient_list": _flags("WA Recipient List"),
	}


def list_profiles(account: str | None = None, query: str | None = None) -> list[dict]:
	if not _doctype_exists("WA Profile"):
		return []
	frappe.has_permission("WA Profile", "read", throw=True)
	filters: dict = {}
	account_name = (account or "").strip()
	if account_name:
		filters["whatsapp_account"] = account_name
	rows = _get_list(
		"WA Profile",
		filters=filters,
		or_filters=_search_filters(("profile_name", "phone_number", "name"), query),
		fields=["name", "profile_name", "phone_number", "whatsapp_account", "status"],
	)
	return [_profile_from_row(row) for row in rows]


def save_profile(
	name: str | None = None,
	profile_name: str | None = None,
	phone_number: str | None = None,
	whatsapp_account: str | None = None,
	status: str | None = None,
) -> dict:
	"""Create a profile, or update one the user is allowed to write.

	A new number that already exists on this account is returned instead of
	inserted again. The name is updated only when the user can write.
	"""
	_require_doctype("WA Profile", _("WhatsApp profiles are not installed on this site."))
	phone = profile_phone(phone_number)
	_require_phone(phone)
	label = (profile_name or "").strip() or phone
	chosen = (status or "").strip() or "Active"
	if chosen not in PROFILE_STATUSES:
		frappe.throw(_("Status must be Active, Blocked, or Archived."))
	account_name = _assert_account(whatsapp_account, required=True)
	record = (name or "").strip()
	created = False
	from nudg.utils.phone import find_matching_profile

	if record:
		if not frappe.db.exists("WA Profile", record):
			frappe.throw(_("Contact not found."))
		doc = frappe.get_doc("WA Profile", record)
		frappe.has_permission("WA Profile", "write", doc=doc, throw=True)
		other = find_matching_profile(phone, account_name)
		if other and other != doc.name:
			frappe.throw(_("A contact with this number already exists on this WhatsApp account."))
		doc.profile_name = label
		doc.phone_number = phone
		doc.whatsapp_account = account_name
		doc.status = chosen
		doc.save()
	else:
		other = find_matching_profile(phone, account_name)
		if other:
			doc = frappe.get_doc("WA Profile", other)
			frappe.has_permission("WA Profile", "read", doc=doc, throw=True)
			if label != (doc.profile_name or "") and frappe.has_permission("WA Profile", "write", doc=doc):
				doc.profile_name = label
				doc.save()
		else:
			frappe.has_permission("WA Profile", "create", throw=True)
			doc = frappe.new_doc("WA Profile")
			doc.profile_name = label
			doc.phone_number = phone
			doc.whatsapp_account = account_name
			doc.status = chosen
			doc.insert()
			created = True
	return {**_profile_from_doc(doc), "created": created}


def delete_profile(name: str) -> dict:
	record = (name or "").strip()
	if not record or not frappe.db.exists("WA Profile", record):
		frappe.throw(_("Contact not found."))
	doc = frappe.get_doc("WA Profile", record)
	frappe.has_permission("WA Profile", "delete", doc=doc, throw=True)
	frappe.delete_doc("WA Profile", record)
	return {"name": record, "deleted": True}


def list_recipient_lists(account: str | None = None, query: str | None = None) -> list[dict]:
	if not _doctype_exists("WA Recipient List"):
		return []
	frappe.has_permission("WA Recipient List", "read", throw=True)
	account_name = (account or "").strip()
	rows = _get_list(
		"WA Recipient List",
		filters={},
		or_filters=_search_filters(("list_name", "description", "name"), query),
		fields=["name", "list_name", "description", "whatsapp_account"],
	)
	if account_name:
		rows = [
			row
			for row in rows
			if not row.get("whatsapp_account") or row.get("whatsapp_account") == account_name
		]
	counts = _recipient_counts([row.get("name") for row in rows if row.get("name")])
	result = []
	for row in rows:
		item = _list_from_row(row)
		item["recipient_count"] = counts.get(item["name"], 0)
		result.append(item)
	return result


def get_recipient_list(name: str) -> dict:
	record = (name or "").strip()
	if not record or not frappe.db.exists("WA Recipient List", record):
		frappe.throw(_("Recipient list not found."))
	doc = frappe.get_doc("WA Recipient List", record)
	frappe.has_permission("WA Recipient List", "read", doc=doc, throw=True)
	return _list_from_doc(doc, include_recipients=True)


def save_recipient_list(
	name: str | None = None,
	list_name: str | None = None,
	description: str | None = None,
	whatsapp_account: str | None = None,
	recipients: str | list | None = None,
) -> dict:
	_require_doctype("WA Recipient List", _("Recipient lists are not installed on this site."))
	title = (list_name or "").strip()
	if not title:
		frappe.throw(_("Enter a list name."))
	account_name = _assert_account(whatsapp_account, required=False)
	rows = _recipient_payload(recipients)
	record = (name or "").strip()
	created = False
	if record:
		if not frappe.db.exists("WA Recipient List", record):
			frappe.throw(_("Recipient list not found."))
		doc = frappe.get_doc("WA Recipient List", record)
		frappe.has_permission("WA Recipient List", "write", doc=doc, throw=True)
	else:
		frappe.has_permission("WA Recipient List", "create", throw=True)
		if frappe.db.exists("WA Recipient List", title):
			frappe.throw(_("A recipient list with this name already exists."))
		doc = frappe.new_doc("WA Recipient List")
		created = True
	previous = {}
	if not created:
		for row in doc.recipients or []:
			previous[normalize_mobile_no(row.mobile_number)] = row.recipient_data
	doc.list_name = title
	doc.description = (description or "").strip()
	doc.whatsapp_account = account_name or None
	doc.set("recipients", [])
	for row in rows:
		mobile = profile_phone(row.get("mobile_number"))
		_require_phone(mobile, _("Each recipient needs a valid mobile number."))
		doc.append(
			"recipients",
			{
				"mobile_number": mobile,
				"recipient_name": (row.get("recipient_name") or "").strip(),
				"unsubscribed": 1 if cint(row.get("unsubscribed")) else 0,
				"recipient_data": previous.get(normalize_mobile_no(mobile)),
			},
		)
	if created:
		doc.insert()
	else:
		doc.save()
	payload = _list_from_doc(doc, include_recipients=True)
	payload["created"] = created
	return payload


def delete_recipient_list(name: str) -> dict:
	record = (name or "").strip()
	if not record or not frappe.db.exists("WA Recipient List", record):
		frappe.throw(_("Recipient list not found."))
	doc = frappe.get_doc("WA Recipient List", record)
	frappe.has_permission("WA Recipient List", "delete", doc=doc, throw=True)
	frappe.delete_doc("WA Recipient List", record)
	return {"name": record, "deleted": True}


def profile_phone(number: str | None) -> str:
	"""Same phone shape as a WhatsApp profile, with a digits fallback."""
	raw = (number or "").strip()
	if not raw:
		return ""
	try:
		from whatsapp.whatsapp.doctype.wa_profile.wa_profile import normalize_phone

		normalized = normalize_phone(raw)
		if normalized:
			return normalized
	except Exception:
		pass
	digits = normalize_mobile_no(raw)
	return f"+{digits}" if digits else ""


def _flags(doctype: str) -> dict[str, bool]:
	blank = {ptype: False for ptype in PTYPES}
	if not _doctype_exists(doctype):
		return blank
	out = {}
	for ptype in PTYPES:
		try:
			out[ptype] = bool(frappe.has_permission(doctype, ptype))
		except Exception:
			out[ptype] = False
	return out


def _doctype_exists(doctype: str) -> bool:
	try:
		return bool(frappe.db.exists("DocType", doctype))
	except Exception:
		return False


def _require_doctype(doctype: str, message: str) -> None:
	if not _doctype_exists(doctype):
		frappe.throw(message)


def _require_phone(phone: str, message: str | None = None) -> None:
	if len(normalize_mobile_no(phone)) < 8:
		frappe.throw(message or _("Enter a valid phone number."))


def _assert_account(account: str | None, required: bool) -> str:
	account_name = (account or "").strip()
	if not account_name:
		if required:
			frappe.throw(_("Choose a WhatsApp account."))
		return ""
	if not frappe.db.exists("WA Account", account_name):
		frappe.throw(_("WhatsApp account {0} was not found.").format(account_name))
	from nudg.security import has_tenant_permission

	probe = frappe._dict(doctype="WA Profile", whatsapp_account=account_name)
	if not has_tenant_permission(probe, "read"):
		frappe.throw(_("You cannot use this WhatsApp account."), frappe.PermissionError)
	return account_name


def _search_filters(fields: tuple[str, ...], query: str | None) -> list | None:
	text = re.sub(r"[%_\\]", "", (query or "").strip())[:80]
	if not text:
		return None
	like = f"%{text}%"
	return [[field, "like", like] for field in fields]


def _get_list(doctype: str, filters: dict, or_filters: list | None, fields: list[str]) -> list[dict]:
	kwargs = {
		"filters": filters,
		"fields": fields,
		"order_by": "modified desc",
		"limit_page_length": 200,
	}
	if or_filters:
		kwargs["or_filters"] = or_filters
	rows = frappe.get_list(doctype, **kwargs)
	return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _profile_from_row(row: dict) -> dict:
	return {
		"name": row.get("name") or "",
		"profile_name": row.get("profile_name") or "",
		"phone_number": row.get("phone_number") or "",
		"whatsapp_account": row.get("whatsapp_account") or "",
		"status": row.get("status") or "Active",
	}


def _profile_from_doc(doc) -> dict:
	return _profile_from_row(
		{
			"name": doc.name,
			"profile_name": doc.profile_name,
			"phone_number": doc.phone_number,
			"whatsapp_account": doc.whatsapp_account,
			"status": doc.status,
		}
	)


def _list_from_row(row: dict) -> dict:
	return {
		"name": row.get("name") or "",
		"list_name": row.get("list_name") or row.get("name") or "",
		"description": row.get("description") or "",
		"whatsapp_account": row.get("whatsapp_account") or "",
		"recipient_count": int(row.get("recipient_count") or 0),
	}


def _list_from_doc(doc, include_recipients: bool = False) -> dict:
	recipients = [
		{
			"mobile_number": row.mobile_number or "",
			"recipient_name": row.recipient_name or "",
			"unsubscribed": 1 if row.unsubscribed else 0,
		}
		for row in (doc.recipients or [])
	]
	payload = {
		"name": doc.name,
		"list_name": doc.list_name or doc.name,
		"description": doc.description or "",
		"whatsapp_account": doc.whatsapp_account or "",
		"recipient_count": len(recipients),
	}
	if include_recipients:
		payload["recipients"] = recipients
	return payload


def _recipient_payload(value: str | list | None) -> list[dict]:
	if value is None or value == "":
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except json.JSONDecodeError:
			frappe.throw(_("Recipients must be a list."))
	if not isinstance(value, list):
		frappe.throw(_("Recipients must be a list."))
	rows = []
	for row in value:
		if isinstance(row, dict):
			rows.append(row)
	return rows


def _recipient_counts(names: list[str]) -> dict[str, int]:
	if not names:
		return {}
	try:
		raw = frappe.db.sql(
			"""
			SELECT parent, COUNT(*) AS total
			FROM `tabWA Recipient`
			WHERE parenttype = 'WA Recipient List' AND parent IN %(names)s
			GROUP BY parent
			""",
			{"names": tuple(names)},
			as_dict=True,
		)
	except Exception:
		return {}
	counts: dict[str, int] = {}
	for row in raw or []:
		if not isinstance(row, dict) or not row.get("parent"):
			continue
		counts[row["parent"]] = int(row.get("total") or 0)
	return counts
