# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Titles for screens. Document ids stay in the API and never become the label."""

from __future__ import annotations

import frappe


def bulk_display_title(stored: str | None, campaign_label: str | None, template_label: str | None) -> str:
	text = (stored or "").strip()
	if text and not text.startswith("WA-CAMP-") and not text.startswith("BULK-WA-"):
		return text
	parts = [part for part in ((campaign_label or "").strip(), (template_label or "").strip()) if part]
	return " · ".join(parts) or "Bulk message"


def template_titles(names: list[str]) -> dict[str, str]:
	unique = [name for name in dict.fromkeys(names) if name]
	if not unique or not frappe.db.exists("DocType", "WA Template"):
		return {}
	rows = frappe.get_all(
		"WA Template",
		filters={"name": ["in", unique]},
		fields=["name", "template_label", "template_name"],
		limit_page_length=len(unique),
	)
	titles = {}
	for row in rows or []:
		titles[row.name] = (row.template_label or row.template_name or "").strip() or "Untitled template"
	return titles


def account_titles(names: list[str]) -> dict[str, str]:
	unique = [name for name in dict.fromkeys(names) if name]
	if not unique or not frappe.db.exists("DocType", "WA Account"):
		return {}
	rows = frappe.get_all(
		"WA Account",
		filters={"name": ["in", unique]},
		fields=["name", "account_name"],
		limit_page_length=len(unique),
	)
	return {row.name: (row.account_name or "").strip() or "WhatsApp account" for row in (rows or [])}


def audience_title(recipient_type: str | None, recipient: str | None) -> str:
	if not recipient:
		return ""
	if recipient_type == "WA Recipient List" and frappe.db.exists("DocType", "WA Recipient List"):
		title = frappe.db.get_value("WA Recipient List", recipient, "list_name")
		return (title or "").strip() or "Recipient list"
	if recipient_type == "WA Profile" and frappe.db.exists("DocType", "WA Profile"):
		row = frappe.db.get_value("WA Profile", recipient, ["profile_name", "phone_number"], as_dict=True) or {}
		name = (row.get("profile_name") or "").strip() or "Contact"
		phone = (row.get("phone_number") or "").strip()
		return f"{name} · {phone}" if phone else name
	return ""
