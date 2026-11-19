# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Hermetic unit tests for STOP consent and duplicate inbound messages."""

from __future__ import annotations

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

	def test_duplicate_inbound_id_is_rejected(self):
		from nudg.services.automation import guard_duplicate_inbound

		doc = frappe._dict(direction="Incoming", message_id="wamid.HELLO", name=None)
		self.mock_db.sql.return_value = (("MSG-1",),)
		with self.assertRaises(frappe.DuplicateEntryError):
			guard_duplicate_inbound(doc)

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
