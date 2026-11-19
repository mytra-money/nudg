# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Outgoing WhatsApp messages use the recipient profile's number."""

from __future__ import annotations

import frappe
from frappe.utils import cint


def bind_outgoing_account(doc, method=None) -> None:
	"""Send on the profile's WhatsApp account, not the site default.

	The official app fills a blank account from ``WA Settings.default_account``
	in ``WA Message.before_insert``, and the desk form does the same. A profile
	belongs to one number, so that default is the wrong sender whenever the
	profile is on another account. This runs on save and on submit, after that
	default is applied and before the official validate copies ``phone_id``.
	"""
	if getattr(doc, "direction", None) != "Outgoing":
		return

	status = cint(getattr(doc, "docstatus", 0) or 0)
	action = getattr(doc, "_action", None)
	if status == 2 or (status == 1 and action != "submit"):
		return

	profile = (doc.get("to") or "").strip()
	if not profile:
		return

	account = _profile_account(profile)
	if not account:
		return

	phone_id = _phone_id(account)
	if doc.get("whatsapp_account") == account:
		if phone_id and doc.get("from") != phone_id:
			doc.set("from", phone_id)
		return

	doc.whatsapp_account = account
	doc.set("from", phone_id or None)


def _profile_account(profile: str) -> str | None:
	value = frappe.db.get_value("WA Profile", profile, "whatsapp_account")
	return str(value) if value else None


def _phone_id(account: str) -> str | None:
	value = frappe.db.get_value("WA Account", account, "phone_id")
	return str(value) if value else None
