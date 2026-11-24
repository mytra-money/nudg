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


def stop_plan(phone: str | None, campaign: dict) -> dict:
	"""Who a reply unsubscribes, and whether the campaign itself should stop.

	The campaign must have asked for this, still be running, and already have
	sent a step. A reply before the first send leaves the audience alone.
	Other recipients stay on the campaign. The campaign is cancelled only when
	nobody subscribed remains.
	"""
	empty = {"campaign_rows": [], "list_rows": [], "cancel": False}
	if not campaign.get("stop_on_reply"):
		return empty
	if str(campaign.get("status") or "") in ("Completed", "Cancelled"):
		return empty
	if not campaign.get("has_dispatch"):
		return empty
	digits = phone_digits(phone)
	if not digits:
		return empty
	campaign_rows: list[str] = []
	matched = False
	subscribed_left = 0
	for row in campaign.get("recipients") or []:
		same = phone_digits(row.get("mobile_number")) == digits
		flagged = int(row.get("unsubscribed") or 0) == 1
		if same:
			matched = True
			if not flagged and row.get("name"):
				campaign_rows.append(row["name"])
			flagged = True
		if not flagged:
			subscribed_left += 1
	if not matched:
		return empty
	list_rows: list[str] = []
	if campaign.get("recipient_type") == "WA Recipient List":
		for row in campaign.get("list_recipients") or []:
			if phone_digits(row.get("mobile_number")) != digits:
				continue
			if int(row.get("unsubscribed") or 0):
				continue
			if row.get("name"):
				list_rows.append(row["name"])
	cancel = subscribed_left == 0 and bool(campaign.get("recipients"))
	return {"matched": True, "campaign_rows": campaign_rows, "list_rows": list_rows, "cancel": cancel}


def apply_unsubscribe(source_rows, submitted_rows, remembered: dict | None = None, previous=None):
	"""Keep a checkbox the user changed, and keep a tick already stored on the list.

	Returns the recipient rows to save, and the phone numbers whose checkbox
	changed so the same tick can be written onto recipient lists.
	"""
	remembered = remembered or {}
	submitted: dict[str, tuple] = {}
	for row in submitted_rows or []:
		phone = _row_phone(row)
		digits = phone_digits(phone)
		if digits:
			submitted[digits] = (phone, _row_flag(row))
	previous_flags = None
	if previous is not None:
		previous_flags = {}
		for row in previous:
			digits = phone_digits(_row_phone(row))
			if digits:
				previous_flags[digits] = _row_flag(row)
	merged = []
	edits = []
	for row in source_rows or []:
		copy = dict(row)
		phone = copy.get("mobile_number")
		digits = phone_digits(phone)
		source_flag = 1 if copy.get("unsubscribed") else 0
		remembered_flag = 1 if digits and remembered.get(digits) else 0
		if digits and digits in submitted:
			want = submitted[digits][1]
			baseline = source_flag if previous_flags is None else previous_flags.get(digits, remembered_flag)
			if want != baseline:
				edits.append((submitted[digits][0] or phone, want))
				copy["unsubscribed"] = want
			else:
				copy["unsubscribed"] = 1 if (source_flag or remembered_flag or want) else 0
		else:
			copy["unsubscribed"] = 1 if (source_flag or remembered_flag) else 0
		merged.append(copy)
	return merged, edits


def _row_phone(row) -> str | None:
	if isinstance(row, dict):
		return row.get("mobile_number")
	return getattr(row, "mobile_number", None)


def _row_flag(row) -> int:
	value = row.get("unsubscribed") if isinstance(row, dict) else getattr(row, "unsubscribed", 0)
	return 1 if value else 0


def stop_drip_on_reply(phone: str | None) -> int:
	"""Tick Unsubscribed for this phone on campaigns that stop when a customer replies."""
	if not phone or not frappe.db.exists("DocType", "WA Campaign"):
		return 0
	if not frappe.db.has_column("WA Campaign", "stop_on_reply"):
		return 0
	if not frappe.db.exists("DocType", "WA Recipient"):
		return 0
	names = frappe.get_all(
		"WA Campaign",
		filters={"stop_on_reply": 1, "status": ["not in", ["Completed", "Cancelled"]]},
		pluck="name",
	)
	if not isinstance(names, list):
		return 0
	changed = 0
	for name in names:
		changed += _stop_one_campaign(name, phone)
	return changed


def _stop_one_campaign(name: str, phone: str) -> int:
	meta = frappe.db.get_value("WA Campaign", name, ["status", "recipient_type", "recipient"], as_dict=True) or {}
	recipients = frappe.get_all(
		"WA Recipient",
		filters={"parent": name, "parenttype": "WA Campaign"},
		fields=["name", "mobile_number", "unsubscribed"],
		limit_page_length=0,
	)
	list_recipients: list[dict] = []
	if meta.get("recipient_type") == "WA Recipient List" and meta.get("recipient"):
		list_recipients = frappe.get_all(
			"WA Recipient",
			filters={"parent": meta.get("recipient"), "parenttype": "WA Recipient List"},
			fields=["name", "mobile_number", "unsubscribed"],
			limit_page_length=0,
		)
		if not isinstance(list_recipients, list):
			list_recipients = []
	if not isinstance(recipients, list):
		recipients = []
	plan = stop_plan(
		phone,
		{
			"stop_on_reply": 1,
			"status": meta.get("status"),
			"has_dispatch": _campaign_has_dispatch(name),
			"recipient_type": meta.get("recipient_type"),
			"recipients": recipients,
			"list_recipients": list_recipients,
		},
	)
	if not plan.get("matched"):
		return 0
	# Any reply stops the rest of the drip. No confirmation is sent.
	# The tick is written on this campaign and on every recipient list for the phone.
	changed = set_audience_unsubscribed(phone, 1)
	if plan["cancel"]:
		frappe.db.set_value("WA Campaign", name, "status", "Cancelled", update_modified=False)
	return changed


def _campaign_has_dispatch(name: str) -> bool:
	if not frappe.db.exists("DocType", "WA Campaign Dispatch"):
		return False
	rows = frappe.get_all(
		"WA Campaign Dispatch",
		filters={"parent": name, "parenttype": "WA Campaign"},
		fields=["bulk_message"],
		limit_page_length=0,
	)
	if not isinstance(rows, list):
		return False
	return any(row.get("bulk_message") for row in rows)


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
