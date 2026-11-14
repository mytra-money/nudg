# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

"""Phone normalization, matching keys, and standard Profile lookup."""

from __future__ import annotations

import re
import frappe


def normalize_mobile_no(number: str | None) -> str:
	"""Normalize phone numbers to digits only without leading '+' or formatting symbols."""
	if not number:
		return ""

	cleaned = str(number).strip()
	if cleaned.startswith("+"):
		cleaned = cleaned[1:]

	# Keep digits only
	cleaned = re.sub(r"\D", "", cleaned)
	return cleaned


def phone_match_key(number: str | None) -> str:
	"""Extract trailing 10 digits for reliable cross-field phone matching."""
	normalized = normalize_mobile_no(number)
	if len(normalized) >= 10:
		return normalized[-10:]
	return normalized


def normalized_message_filter(field_name: str, param_name: str = "normalized_no") -> str:
	"""SQL expression to compare a message from/to field against a normalized number."""
	return (
		f"REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(IFNULL(`{field_name}`, ''), '+', ''), "
		f"' ', ''), '-', ''), '(', ''), ')', '') = %({param_name})s"
	)


def find_matching_profile(mobile_no: str, account: str | None = None) -> str | None:
	"""Find WA Profile by number, handling +91 vs 91 and formatting differences."""
	normalized = normalize_mobile_no(mobile_no)
	if not normalized:
		return None

	filters: dict = {}
	if account:
		filters["whatsapp_account"] = account

	# Exact match check first
	for candidate in (normalized, f"+{normalized}"):
		filters["phone_number"] = candidate
		name = frappe.db.get_value("WA Profile", filters, "name")
		if name:
			return name

	# Suffix 10-digit fallback
	suffix = phone_match_key(normalized)
	query = """
		SELECT name
		FROM `tabWA Profile`
		WHERE REPLACE(REPLACE(IFNULL(phone_number, ''), '+', ''), ' ', '') LIKE %(pattern)s
	"""
	params = {"pattern": f"%{suffix}"}
	if account:
		query += " AND whatsapp_account = %(account)s"
		params["account"] = account

	query += " ORDER BY modified DESC LIMIT 1"
	rows = frappe.db.sql(query, params)
	return rows[0][0] if rows else None
