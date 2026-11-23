# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Set the Unsubscribed checkbox from a keyword rule.

The word itself is configured on a Keyword rule. This only updates audience
rows. It does not change the WhatsApp profile status.
"""

from __future__ import annotations

import re

import frappe


def phone_digits(phone: str | None) -> str:
	return re.sub(r"\D", "", str(phone or ""))


def set_audience_unsubscribed(phone: str | None, unsubscribed: int) -> int:
	"""Tick or clear Unsubscribed on every audience row for this phone."""
	digits = phone_digits(phone)
	if not digits or not frappe.db.exists("DocType", "WA Recipient"):
		return 0
	if not frappe.db.has_column("WA Recipient", "unsubscribed"):
		return 0
	rows = frappe.get_all(
		"WA Recipient",
		filters={"parenttype": ["in", ["WA Campaign", "WA Recipient List"]]},
		fields=["name", "mobile_number", "unsubscribed"],
		limit_page_length=0,
	)
	if not isinstance(rows, list):
		return 0
	changed = 0
	flag = 1 if unsubscribed else 0
	for row in rows:
		if phone_digits(row.get("mobile_number")) != digits:
			continue
		if int(row.get("unsubscribed") or 0) == flag:
			continue
		frappe.db.set_value("WA Recipient", row.get("name"), "unsubscribed", flag, update_modified=False)
		changed += 1
	return changed


def remembered_unsubscribed(campaign: str | None) -> dict[str, int]:
	"""Phone digits already unchecked on this campaign, so a save does not clear them."""
	if not campaign or not frappe.db.exists("DocType", "WA Recipient"):
		return {}
	if not frappe.db.has_column("WA Recipient", "unsubscribed"):
		return {}
	rows = frappe.get_all(
		"WA Recipient",
		filters={"parent": campaign, "parenttype": "WA Campaign", "unsubscribed": 1},
		fields=["mobile_number"],
		limit_page_length=0,
	)
	if not isinstance(rows, list):
		return {}
	return {phone_digits(row.get("mobile_number")): 1 for row in rows if phone_digits(row.get("mobile_number"))}
