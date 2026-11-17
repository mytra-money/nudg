# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Hermetic unit tests for Keyword Automation, Business Hours & STOP Consent compliance."""

from __future__ import annotations

import datetime
import json
import unittest
from unittest.mock import MagicMock, patch
import zoneinfo

import frappe


class TestAutomationCompliance(unittest.TestCase):
	"""Test suite for Keyword triggers, Business Hours evaluation, and Consent management."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "cache", "valid_columns"):
			self._saved[name] = getattr(frappe.local, name, None) if hasattr(frappe, "local") else None
		self._saved_cache = getattr(frappe, "cache", None)

		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Administrator", data=frappe._dict())
		frappe.local.valid_columns = {"WA Account": []}
		self.mock_db = MagicMock()
		self.mock_db.get_table_columns.return_value = []
		frappe.local.db = self.mock_db
		self.mock_cache = MagicMock()
		self.mock_cache.get_value.return_value = None
		frappe.cache = MagicMock(return_value=self.mock_cache)

		self.mock_meta = MagicMock()
		self.mock_meta._table_doctypes = {}
		self.mock_meta.has_field.return_value = True
		self.mock_meta.get_field.return_value = None
		self.meta_patch = patch("frappe.get_meta", return_value=self.mock_meta)
		self.meta_patch.start()

	def tearDown(self):
		self.meta_patch.stop()
		frappe.cache = self._saved_cache
		for name in ("flags", "session", "db", "cache", "valid_columns"):
			val = self._saved.get(name)
			if val is not None:
				setattr(frappe.local, name, val)
		super().tearDown()

	# -------------------------------------------------------------------------
	# 1. Keyword Matching Unit Tests
	# -------------------------------------------------------------------------

	def test_window_closed_and_out_of_office_cannot_be_saved(self):
		from nudg.services.automation import _TRIGGERS, create_rule

		self.assertNotIn("Window Closed", _TRIGGERS)
		self.assertNotIn("Out of Office", _TRIGGERS)
		with patch("frappe.has_permission", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				create_rule("Night reply", "Out of Office", "Send Text", action_reference="We are closed")
			with self.assertRaises(frappe.ValidationError):
				create_rule("Closed window", "Window Closed", "Send Template", action_reference="hello")

	def test_keyword_match_exact(self):
		from nudg.services.automation import evaluate_keyword_match

		self.assertTrue(evaluate_keyword_match("HELP", "help", "Exact"))
		self.assertTrue(evaluate_keyword_match("  pricing  ", "pricing", "Exact"))
		self.assertFalse(evaluate_keyword_match("Help me please", "help", "Exact"))
		# Case-sensitive check
		self.assertFalse(evaluate_keyword_match("help", "HELP", "Exact", case_sensitive=True))
		self.assertTrue(evaluate_keyword_match("HELP", "HELP", "Exact", case_sensitive=True))

	def test_keyword_match_contains(self):
		from nudg.services.automation import evaluate_keyword_match

		self.assertTrue(evaluate_keyword_match("Where is my order #12345?", "order", "Contains"))
		self.assertTrue(evaluate_keyword_match("I need support urgently", "SUPPORT", "Contains"))
		self.assertFalse(evaluate_keyword_match("Just saying hello", "refund", "Contains"))

	def test_keyword_match_starts_with(self):
		from nudg.services.automation import evaluate_keyword_match

		self.assertTrue(evaluate_keyword_match("#HELP account issue", "#help", "Starts With"))
		self.assertTrue(evaluate_keyword_match("ORDER 99281", "order", "Starts With"))
		self.assertFalse(evaluate_keyword_match("my ORDER 99281", "order", "Starts With"))

	def test_keyword_match_regex(self):
		from nudg.services.automation import evaluate_keyword_match

		pattern = r"^ORDER[-_]\d{4,6}$"
		self.assertTrue(evaluate_keyword_match("ORDER-12345", pattern, "Regex"))
		self.assertTrue(evaluate_keyword_match("order_9999", pattern, "Regex"))
		self.assertFalse(evaluate_keyword_match("ORDER-abc", pattern, "Regex"))
		# Invalid regex should fail gracefully without crashing
		self.assertFalse(evaluate_keyword_match("test", r"[unclosed", "Regex"))

	def test_keyword_match_multiple_values(self):
		from nudg.services.automation import evaluate_keyword_match

		keywords = ["hi", "hello", "hey", "greetings"]
		self.assertTrue(evaluate_keyword_match("Hello there!", keywords, "Contains"))
		self.assertTrue(evaluate_keyword_match("hey", keywords, "Exact"))
		self.assertFalse(evaluate_keyword_match("goodbye", keywords, "Contains"))

	def test_condition_matches_composite(self):
		from nudg.services.automation import _condition_matches

		doc = {
			"message": "Can I get a refund for my item?",
			"direction": "Incoming",
			"status": "Sent",
		}

		# Nested keyword condition + direction equality
		cond_nested = json.dumps({
			"keyword_match": {
				"operator": "Contains",
				"value": "refund",
			},
			"direction": "Incoming",
		})
		self.assertTrue(_condition_matches(cond_nested, doc))

		# Mismatched direction
		cond_mismatch = json.dumps({
			"keyword_match": {
				"operator": "Contains",
				"value": "refund",
			},
			"direction": "Outgoing",
		})
		self.assertFalse(_condition_matches(cond_mismatch, doc))

		# Flat keyword condition
		cond_flat = json.dumps({
			"operator": "Starts With",
			"keyword": "Can I",
		})
		self.assertTrue(_condition_matches(cond_flat, doc))

	# -------------------------------------------------------------------------
	# 2. Consent Management Unit Tests
	# -------------------------------------------------------------------------

	def test_evaluate_consent_keywords(self):
		from nudg.services.consent import evaluate_consent_keyword

		# Opt-Out keywords
		for kw in ("STOP", "stop", "UNSUBSCRIBE", "cancel", "QUIT", "end", "STOPALL"):
			status, matched = evaluate_consent_keyword(kw)
			self.assertEqual(status, "Opted-Out", f"Keyword {kw} failed opt-out match")

		# Opt-In keywords
		for kw in ("START", "start", "UNSTOP", "unstop", "OPTIN"):
			status, matched = evaluate_consent_keyword(kw)
			self.assertEqual(status, "Opted-In", f"Keyword {kw} failed opt-in match")

		# Punctuation tolerance
		self.assertEqual(evaluate_consent_keyword("STOP!")[0], "Opted-Out")
		self.assertEqual(evaluate_consent_keyword("#start")[0], "Opted-In")

		# Non-consent regular conversation
		self.assertIsNone(evaluate_consent_keyword("Hello, when does the bus stop?")[0])
		self.assertIsNone(evaluate_consent_keyword("Can you start my subscription?")[0])

	def test_handle_incoming_consent(self):
		from nudg.services.consent import handle_incoming_consent

		with patch("nudg.integrations.repository.contact_repo.DeskContactRepository.update_consent") as mock_upd:
			with patch("nudg.services.consent._send_consent_acknowledgment") as mock_ack:
				is_consent, status = handle_incoming_consent(
					contact_id="WA-CONT-001",
					text="STOP",
					channel_doc={"name": "Channel 1"},
					phone_number="+15551234567",
					send_acknowledgment=True,
				)
				self.assertTrue(is_consent)
				self.assertEqual(status, "Opted-Out")
				mock_upd.assert_called_once_with(
					"WA-CONT-001",
					"Opted-Out",
					reason="STOP keyword",
				)
				mock_ack.assert_called_once()


if __name__ == "__main__":
	unittest.main()
