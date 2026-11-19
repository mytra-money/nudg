# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Match an incoming message against WA Keyword Reply rules."""

from __future__ import annotations

import re
from datetime import datetime

import frappe


def rule_matches(rule, message_text: str) -> bool:
	"""True when one keyword in the rule matches the message."""
	if not message_text or not getattr(rule, "keywords", None):
		return False

	keywords = [part.strip() for part in str(rule.keywords).split(",") if part.strip()]
	case_sensitive = bool(getattr(rule, "case_sensitive", 0))
	text = message_text if case_sensitive else message_text.lower()
	match_type = getattr(rule, "match_type", None) or "Contains"

	for keyword in keywords:
		probe = keyword if case_sensitive else keyword.lower()
		if match_type == "Exact" and text == probe:
			return True
		if match_type == "Contains" and probe in text:
			return True
		if match_type == "Starts With" and text.startswith(probe):
			return True
		if match_type == "Regex":
			flags = 0 if case_sensitive else re.IGNORECASE
			try:
				if re.search(keyword, message_text, flags):
					return True
			except re.error:
				frappe.log_error(title=f"Invalid keyword regex: {getattr(rule, 'name', keyword)}")
	return False


def evaluate_conditions(conditions: str, message_text: str) -> bool:
	"""Evaluate an optional safe expression. `message` is the only input."""
	if not conditions:
		return True
	try:
		return bool(
			frappe.safe_eval(
				conditions,
				eval_globals={"message": message_text, "len": len, "str": str, "int": int, "float": float, "bool": bool},
				eval_locals={},
			)
		)
	except Exception:
		frappe.log_error(title="Keyword condition failed")
		return False


def _as_datetime(value):
	if not value or isinstance(value, datetime):
		return value
	if isinstance(value, str):
		from frappe.utils import get_datetime

		return get_datetime(value)
	return value


def _in_window(rule, now: datetime) -> bool:
	start = _as_datetime(rule.get("active_from") if isinstance(rule, dict) else getattr(rule, "active_from", None))
	end = _as_datetime(rule.get("active_until") if isinstance(rule, dict) else getattr(rule, "active_until", None))
	if start and now < start:
		return False
	if end and now > end:
		return False
	return True


class KeywordMatcher:
	"""Active keyword rules for one WhatsApp account, highest priority first."""

	def __init__(self, whatsapp_account=None):
		self.account = whatsapp_account
		self.rules = self.load_rules()

	def load_rules(self):
		try:
			rows = frappe.get_all(
				"WA Keyword Reply",
				filters={"enabled": 1},
				fields=["*"],
				order_by="priority desc",
			)
		except Exception:
			frappe.log_error(title="Keyword rules could not be loaded")
			return []

		now = datetime.now()
		kept = []
		for rule in rows:
			account = rule.get("whatsapp_account") if isinstance(rule, dict) else rule.whatsapp_account
			if not self.account or account != self.account:
				continue
			if not _in_window(rule, now):
				continue
			kept.append(rule)
		return kept

	def match(self, message_text: str):
		"""Return the matching WA Keyword Reply document, or None."""
		if not message_text:
			return None
		for rule in self.rules:
			name = rule.get("name") if isinstance(rule, dict) else rule.name
			if not rule_matches(rule, message_text):
				continue
			conditions = rule.get("conditions") if isinstance(rule, dict) else rule.conditions
			if conditions and not evaluate_conditions(conditions, message_text):
				continue
			return frappe.get_doc("WA Keyword Reply", name)
		return None
