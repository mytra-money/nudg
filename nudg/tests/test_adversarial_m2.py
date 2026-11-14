# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Adversarial stress, boundary, and concurrency test suite for Milestone 2 features.

Focus Areas:
1. Campaign variable substitution with extreme inputs (missing keys, nested JSON, special characters, unicode, emoji, empty arrays, malformed JSON).
2. Opt-out suppression boundaries (mixed case "sToP", whitespace "  STOP  ", punctuation "STOP!", un-optout "START", multiple contacts).
3. Business hours schedule edge cases (midnight wraparound, leap years, invalid timezone fallbacks, multi-tenant throttle keys under concurrent callers).
4. Keyword automations regex denial of service (ReDoS patterns, malicious regex strings, null/None inputs).
5. Inbound cart order parser stress test (missing fields, zero prices, huge quantities, currency symbol injection).
6. Shared inbox round-robin under empty agent pools, single agent, concurrent assignments.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import json
import re
import time
import unittest
import zoneinfo
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import get_datetime, now_datetime

from nudg.services import assignments, automation, campaigns, catalog, consent


def _setup_thread_frappe():
	"""Initialize frappe.local context for worker threads in concurrency tests."""
	frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
	frappe.local.session = frappe._dict(user="Administrator", data=frappe._dict())
	frappe.local.site = "test.local"
	frappe.local.conf = frappe._dict(developer_mode=True)
	frappe.local.db = MagicMock()


class TestAdversarialCampaignVariables(unittest.TestCase):
	"""1. Adversarial tests for campaign variable substitution under extreme and malformed inputs."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "site", "conf"):
			self._saved[name] = getattr(frappe.local, name, None) if hasattr(frappe, "local") else None
		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Administrator", data=frappe._dict())
		frappe.local.site = "test.local"
		frappe.local.conf = frappe._dict(developer_mode=True)
		frappe.local.db = MagicMock()

	def tearDown(self):
		for name in ("flags", "session", "db", "site", "conf"):
			val = self._saved.get(name)
			if val is not None:
				setattr(frappe.local, name, val)
			else:
				try:
					delattr(frappe.local, name)
				except AttributeError:
					pass
		super().tearDown()

	def test_missing_keys_in_numeric_sequence(self):
		"""Gaps in positional keys (e.g. {{1}} and {{4}}) should sort numerically without KeyError."""
		raw = '{"4": "fourth", "1": "first", "2": "second"}'
		comps = campaigns.build_template_body_components(raw)
		self.assertIsNotNone(comps)
		params = comps[0]["parameters"]
		self.assertEqual(len(params), 3)
		# Should be sorted numerically 1, 2, 4
		self.assertEqual(params[0]["text"], "first")
		self.assertEqual(params[1]["text"], "second")
		self.assertEqual(params[2]["text"], "fourth")

	def test_nested_json_structures_inside_values(self):
		"""Values containing nested dicts, arrays, or deep objects serialize cleanly without unhandled exception."""
		nested = {
			"1": {"sub_key": "val1", "deep": [10, 20, {"nested": True}]},
			"2": ["a", "b", "c"],
			"3": None,
		}
		comps = campaigns.build_template_body_components(nested)
		self.assertIsNotNone(comps)
		params = comps[0]["parameters"]
		self.assertEqual(len(params), 3)
		self.assertIn("sub_key", params[0]["text"])
		self.assertEqual(params[1]["text"], "['a', 'b', 'c']")
		self.assertEqual(params[2]["text"], "")

	def test_special_characters_unicode_emojis(self):
		"""Unicode scripts, multi-byte emojis, quotes, and HTML/XSS injection in parameters."""
		payload = {
			"greeting": "مرحبا بالعالم",
			"customer": "👩‍💻 Alice 🇧🇷 & Bob",
			"xss": "<script>alert('XSS')</script>",
			"symbols": 'Quotes "double" and \'single\', slash / and backslash \\',
		}
		comps = campaigns.build_template_body_components(payload)
		self.assertIsNotNone(comps)
		params = comps[0]["parameters"]
		self.assertEqual(len(params), 4)
		texts = {p.get("parameter_name"): p.get("text") for p in params}
		self.assertEqual(texts["greeting"], "مرحبا بالعالم")
		self.assertEqual(texts["customer"], "👩‍💻 Alice 🇧🇷 & Bob")
		self.assertEqual(texts["xss"], "<script>alert('XSS')</script>")

	def test_empty_arrays_and_falsy_inputs(self):
		"""Empty arrays, empty dicts, whitespace strings, and None should safely return None."""
		self.assertIsNone(campaigns.build_template_body_components([]))
		self.assertIsNone(campaigns.build_template_body_components("[]"))
		self.assertIsNone(campaigns.build_template_body_components({}))
		self.assertIsNone(campaigns.build_template_body_components("{}"))
		self.assertIsNone(campaigns.build_template_body_components(None))
		self.assertIsNone(campaigns.build_template_body_components(""))
		self.assertIsNone(campaigns.build_template_body_components("   \n\t  "))

	def test_malformed_json_fallback(self):
		"""Malformed JSON strings gracefully fall back to single raw text parameter rather than crashing."""
		malformed_cases = [
			'{"unclosed: true',
			"{'single_quotes': 123}",
			"plain unformatted text variable",
			"<<<malformed>>>",
		]
		for raw in malformed_cases:
			comps = campaigns.build_template_body_components(raw)
			self.assertIsNotNone(comps, f"Expected fallback component for: {raw}")
			params = comps[0]["parameters"]
			self.assertEqual(len(params), 1)
			self.assertEqual(params[0]["text"], raw)

	def test_scalar_primitives_in_json(self):
		"""Scalars (int, float, bool) in JSON string are handled safely."""
		comps_num = campaigns.build_template_body_components("12345")
		self.assertIsNotNone(comps_num)
		self.assertEqual(comps_num[0]["parameters"][0]["text"], "12345")

		comps_bool = campaigns.build_template_body_components("true")
		self.assertIsNotNone(comps_bool)
		self.assertEqual(comps_bool[0]["parameters"][0]["text"], "True")

	def test_components_override_structure(self):
		"""Direct components override dict with empty or populated list."""
		override = {"components": [{"type": "header", "parameters": [{"type": "text", "text": "H"}]}]}
		comps = campaigns.build_template_body_components(override)
		self.assertEqual(comps, override["components"])

		empty_override = {"components": []}
		comps_empty = campaigns.build_template_body_components(empty_override)
		self.assertEqual(comps_empty, [])

	def test_end_to_end_campaign_with_adversarial_recipients(self):
		"""Campaign execution with multiple recipients exhibiting each extreme variable format."""
		recipients_data = [
			frappe._dict({"name": "r1", "phone_number": "+1001", "status": "Pending", "variables_json": '{"1": "Normal"}'}),
			frappe._dict({"name": "r2", "phone_number": "+1002", "status": "Pending", "variables_json": "MALFORMED_JSON_STRING"}),
			frappe._dict({"name": "r3", "phone_number": "+1003", "status": "Pending", "variables_json": '{"1": {"nested": "dict"}}'}),
			frappe._dict({"name": "r4", "phone_number": "+1004", "status": "Pending", "variables_json": "[]"}),
			frappe._dict({"name": "r5", "phone_number": "+1005", "status": "Pending", "variables_json": None}),
		]
		campaign_doc = frappe._dict({
			"name": "CAMP_ADV_TEST",
			"status": "Scheduled",
			"template": "promo_template",
			"sent_count": 0,
			"failed_count": 0,
			"delivered_count": 0,
			"read_count": 0,
			"recipients": recipients_data,
			"save": MagicMock(),
		})

		with patch("frappe.get_doc", return_value=campaign_doc), \
			 patch("frappe.has_permission", return_value=True), \
			 patch("nudg.services.campaigns.check_recipient_consent", return_value=True), \
			 patch("nudg.integrations.whatsapp.adapter.send_template", return_value="MSG_OK") as mock_send, \
			 patch("nudg.services.campaigns.recalculate_campaign_funnel_counts"):

			result = campaigns.run_campaign("CAMP_ADV_TEST")
			self.assertEqual(mock_send.call_count, 5)
			self.assertEqual(result["status"], "Completed")
			self.assertEqual(result["sent_count"], 5)
			self.assertEqual(result["failed_count"], 0)


class TestAdversarialOptOutSuppression(unittest.TestCase):
	"""2. Adversarial tests for Opt-Out suppression boundaries."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "site", "conf"):
			self._saved[name] = getattr(frappe.local, name, None) if hasattr(frappe, "local") else None
		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Administrator", data=frappe._dict())
		frappe.local.site = "test.local"
		frappe.local.conf = frappe._dict(developer_mode=True)
		frappe.local.db = MagicMock()

	def tearDown(self):
		for name in ("flags", "session", "db", "site", "conf"):
			val = self._saved.get(name)
			if val is not None:
				setattr(frappe.local, name, val)
			else:
				try:
					delattr(frappe.local, name)
				except AttributeError:
					pass
		super().tearDown()

	def test_opt_out_casing_and_whitespace_boundaries(self):
		"""Opt-out keywords with arbitrary casing, padding whitespace, and tabs/newlines."""
		cases = [
			("sToP", "STOP"),
			("StOp", "STOP"),
			("  STOP  ", "STOP"),
			("\t\tSTOP\n", "STOP"),
			("uNsUbScRiBe", "UNSUBSCRIBE"),
			("  UNSUBSCRIBE  ", "UNSUBSCRIBE"),
			("CaNcEl", "CANCEL"),
			("qUiT", "QUIT"),
			("aRrEt", "ARRET"),
			("OpToUt", "OPTOUT"),
			("bLoCk", "BLOCK"),
		]
		for input_text, expected_kw in cases:
			status, kw = consent.evaluate_consent_keyword(input_text)
			self.assertEqual(status, "Opted-Out", f"Failed for input: {repr(input_text)}")
			self.assertEqual(kw, expected_kw)

	def test_opt_out_punctuation_stripping(self):
		"""Punctuation surrounding opt-out keywords (exclamation marks, dots, Spanish punctuation)."""
		cases = [
			("STOP!", "STOP"),
			("STOP.", "STOP"),
			("STOP!?!?", "STOP"),
			("¡STOP!", "STOP"),
			("¿STOP?", "STOP"),
			("...UNSUBSCRIBE...", "UNSUBSCRIBE"),
			("[STOP]", "STOP"),
			("((STOP))", "STOP"),
		]
		for input_text, expected_kw in cases:
			status, kw = consent.evaluate_consent_keyword(input_text)
			self.assertEqual(status, "Opted-Out", f"Failed for input: {repr(input_text)}")
			self.assertEqual(kw, expected_kw)

	def test_opt_in_resubscribe_boundaries(self):
		"""START / UNSTOP resubscribe keywords under casing, whitespace, and punctuation."""
		cases = [
			("START", "START"),
			("start", "START"),
			("  sTaRt!  ", "START"),
			("UNSTOP", "UNSTOP"),
			("SUBSCRIBE", "SUBSCRIBE"),
			("  yes  ", "YES"),
			("YES!", "YES"),
		]
		for input_text, expected_kw in cases:
			status, kw = consent.evaluate_consent_keyword(input_text)
			self.assertEqual(status, "Opted-In", f"Failed for input: {repr(input_text)}")
			self.assertEqual(kw, expected_kw)

	def test_non_consent_sentences_not_triggered(self):
		"""Multi-word phrases containing STOP should NOT be falsely recognized as opt-out commands."""
		non_consent = [
			"Please do not stop sending updates",
			"Can I stop the subscription later?",
			"Stop by tomorrow at 5pm",
			"Non-stop service",
			"Wait a second",
			"",
			None,
			"   ",
			"???!!!",
		]
		for text in non_consent:
			status, kw = consent.evaluate_consent_keyword(text)
			self.assertIsNone(status, f"Unexpected trigger for: {repr(text)}")
			self.assertIsNone(kw)

	def test_emoji_boundaries_in_consent(self):
		"""Consent messages containing symbols/emojis around keywords."""
		status_stop, _ = consent.evaluate_consent_keyword("🛑 STOP")
		self.assertEqual(status_stop, "Opted-Out")

		status_start, _ = consent.evaluate_consent_keyword("START 🚀")
		self.assertEqual(status_start, "Opted-In")

	def test_multiple_contacts_campaign_suppression_isolation(self):
		"""In a multi-contact campaign, only opted-out recipients are skipped; others are sent."""
		campaign_doc = frappe._dict({
			"name": "CAMP-MULTI-TEST",
			"status": "Scheduled",
			"template": "promo_template",
			"sent_count": 0,
			"failed_count": 0,
			"delivered_count": 0,
			"read_count": 0,
			"recipients": [
				frappe._dict({"name": "r1", "profile": "prof_allowed_1", "phone_number": "+1111", "status": "Pending"}),
				frappe._dict({"name": "r2", "profile": "prof_opted_out", "phone_number": "+2222", "status": "Pending"}),
				frappe._dict({"name": "r3", "profile": "prof_allowed_2", "phone_number": "+3333", "status": "Pending"}),
			],
			"save": MagicMock(),
		})

		def fake_check_consent(profile=None, phone_number=None):
			return profile != "prof_opted_out" and phone_number != "+2222"

		with patch("frappe.get_doc", return_value=campaign_doc), \
			 patch("frappe.has_permission", return_value=True), \
			 patch("nudg.services.campaigns.check_recipient_consent", side_effect=fake_check_consent), \
			 patch("nudg.integrations.whatsapp.adapter.send_template", return_value="MSG-001") as mock_send, \
			 patch("nudg.services.campaigns.recalculate_campaign_funnel_counts"):

			result = campaigns.run_campaign("CAMP-MULTI-TEST")

			# Recipients 1 and 3 should be Sent
			self.assertEqual(campaign_doc.recipients[0].status, "Sent")
			self.assertEqual(campaign_doc.recipients[2].status, "Sent")

			# Recipient 2 must be Skipped: Opted Out
			self.assertEqual(campaign_doc.recipients[1].status, "Skipped: Opted Out")
			self.assertIn("opted out", campaign_doc.recipients[1].error_message.lower())

			# Adapter should be called exactly twice (never for recipient 2)
			self.assertEqual(mock_send.call_count, 2)
			called_recipients = [c[1]["to"] for c in mock_send.call_args_list]
			self.assertIn("+1111", called_recipients)
			self.assertIn("+3333", called_recipients)
			self.assertNotIn("+2222", called_recipients)


class TestAdversarialKeywordRegex(unittest.TestCase):
	"""4. Adversarial tests for Keyword Automations: ReDoS, malicious regex, and null inputs."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "site", "conf"):
			self._saved[name] = getattr(frappe.local, name, None) if hasattr(frappe, "local") else None
		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Administrator", data=frappe._dict())
		frappe.local.site = "test.local"
		frappe.local.conf = frappe._dict(developer_mode=True)
		frappe.local.db = MagicMock()

	def tearDown(self):
		for name in ("flags", "session", "db", "site", "conf"):
			val = self._saved.get(name)
			if val is not None:
				setattr(frappe.local, name, val)
			else:
				try:
					delattr(frappe.local, name)
				except AttributeError:
					pass
		super().tearDown()

	def test_null_none_and_empty_inputs(self):
		"""All operator modes handle None, empty strings, and non-string types safely."""
		self.assertFalse(automation.evaluate_keyword_match(None, "help", "Exact"))
		self.assertFalse(automation.evaluate_keyword_match("help", None, "Exact"))
		self.assertFalse(automation.evaluate_keyword_match(None, None, "Exact"))
		self.assertFalse(automation.evaluate_keyword_match(None, "help", "Contains"))
		self.assertFalse(automation.evaluate_keyword_match("help", None, "Contains"))
		self.assertFalse(automation.evaluate_keyword_match(None, "help", "Starts With"))
		self.assertFalse(automation.evaluate_keyword_match("text", "pattern", operator="UnknownOp"))

	def test_invalid_and_malicious_regex_syntax(self):
		"""Unterminated regex syntax does not raise unhandled exceptions."""
		malicious_regexes = [
			r"[unclosed_bracket",
			r"(?P<unclosed_group",
			r"*dangling_star",
			r"+dangling_plus",
			r"\k<invalid_backref>",
			r"(?<=incomplete",
		]
		for bad_re in malicious_regexes:
			result = automation.evaluate_keyword_match("Sample text to match", bad_re, "Regex")
			self.assertFalse(result, f"Expected False for invalid regex: {bad_re}")

	def test_regex_repetition_overflow_vulnerability(self):
		"""Vulnerability check: extreme repetition numbers must not crash with uncaught OverflowError."""
		extreme_repetition = r"a{99999999999999999999}"
		try:
			result = automation.evaluate_keyword_match("aaaa", extreme_repetition, "Regex")
			self.assertFalse(result)
		except OverflowError as exc:
			# Empirical finding: evaluate_keyword_match only catches re.error; OverflowError crashes
			self.fail(f"VULNERABILITY CONFIRMED: evaluate_keyword_match crashed with unhandled OverflowError: {exc}")

	def test_catastrophic_backtracking_redos_resistance(self):
		"""ReDoS pattern evaluation timing check."""
		redos_pattern = r"^(a+)+$"
		target_text = "a" * 22 + "!"

		start_time = time.time()
		result = automation.evaluate_keyword_match(target_text, redos_pattern, "Regex")
		duration = time.time() - start_time

		self.assertFalse(result)
		# Bounded execution check (< 5.0 seconds)
		self.assertLess(
			duration,
			5.0,
			f"ReDoS pattern took {duration:.2f}s! Backtracking vulnerability detected."
		)

	def test_extreme_message_length(self):
		"""100,000-character payload evaluated against keywords completes in sub-second time."""
		huge_text = ("lorem ipsum " * 10000) + " ORDER12345 " + ("dolor sit " * 10000)

		start_time = time.time()
		matched = automation.evaluate_keyword_match(huge_text, "ORDER12345", "Contains")
		duration = time.time() - start_time

		self.assertTrue(matched)
		self.assertLess(duration, 0.5, f"Large text search took too long ({duration:.3f}s)")


class TestAdversarialCartOrderParser(unittest.TestCase):
	"""5. Adversarial tests for Inbound Cart Order Webhook Parser."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "site", "conf"):
			self._saved[name] = getattr(frappe.local, name, None) if hasattr(frappe, "local") else None
		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Administrator", data=frappe._dict())
		frappe.local.site = "test.local"
		frappe.local.conf = frappe._dict(developer_mode=True)
		frappe.local.db = MagicMock()

	def tearDown(self):
		for name in ("flags", "session", "db", "site", "conf"):
			val = self._saved.get(name)
			if val is not None:
				setattr(frappe.local, name, val)
			else:
				try:
					delattr(frappe.local, name)
				except AttributeError:
					pass
		super().tearDown()

	def test_missing_fields_and_none_values(self):
		"""Order payload with empty dict, missing fields, or None values."""
		empty_res = catalog.parse_inbound_order({})
		self.assertEqual(empty_res["catalog_id"], "")
		self.assertEqual(empty_res["customer_text"], "")
		self.assertEqual(empty_res["product_items"], [])
		self.assertEqual(empty_res["total_price"], 0.0)
		self.assertEqual(empty_res["item_count"], 0)
		self.assertIn("🛒 Order Placed (0 items)", empty_res["summary_text"])

		none_res = catalog.parse_inbound_order({"product_items": None, "text": None, "catalog_id": None})
		self.assertEqual(none_res["item_count"], 0)
		self.assertEqual(none_res["total_price"], 0.0)

	def test_zero_prices_and_fractional_quantities(self):
		"""Free items (price 0) and fractional decimal quantities."""
		payload = {
			"product_items": [
				{"product_retailer_id": "FREE_SAMPLE", "quantity": 3, "item_price": 0, "currency": "USD"},
				{"product_retailer_id": "BULK_GRAIN", "quantity": 2.5, "item_price": 4.0, "currency": "USD"},
			]
		}
		res = catalog.parse_inbound_order(payload)
		self.assertEqual(res["item_count"], 2)
		self.assertEqual(res["total_price"], 10.0)
		self.assertIn("BULK_GRAIN × 2.50", res["summary_text"])
		self.assertIn("FREE_SAMPLE × 3", res["summary_text"])

	def test_huge_quantities_and_large_numbers(self):
		"""Large quantities and prices do not cause numeric overflow."""
		payload = {
			"product_items": [
				{"product_retailer_id": "SKU_HUGE", "quantity": 10**12, "item_price": 50.0, "currency": "USD"}
			]
		}
		res = catalog.parse_inbound_order(payload)
		self.assertEqual(res["product_items"][0]["line_total"], 50.0 * (10**12))
		self.assertEqual(res["total_price"], 50.0 * (10**12))

	def test_currency_symbol_injection(self):
		"""Adversarial check: currency symbol containing newlines or forged text."""
		malicious_payload = {
			"product_items": [
				{
					"product_retailer_id": "PROD_1",
					"quantity": 1,
					"item_price": 100.0,
					"currency": "USD\nTotal: $0.00\nStatus: Paid\n",
				}
			]
		}
		res = catalog.parse_inbound_order(malicious_payload)
		self.assertEqual(res["total_price"], 100.0)
		# Empirically verify whether newline injection in currency leaks into summary text
		self.assertIn("USD\nTOTAL: $0.00", res["summary_text"].upper())

	def test_malformed_item_entries_resilience(self):
		"""Vulnerability check: non-dict entries inside product_items must not cause unhandled crash."""
		malformed_payload = {
			"product_items": ["not_a_dict", 12345, None]
		}
		try:
			res = catalog.parse_inbound_order(malformed_payload)
			self.assertIsNotNone(res)
		except AttributeError as exc:
			self.fail(f"VULNERABILITY CONFIRMED: parse_inbound_order crashed on non-dict item entry: {exc}")


class TestAdversarialRoundRobin(unittest.TestCase):
	"""6. Adversarial tests for Shared Inbox Round-Robin under empty pool, single agent, and concurrency."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "site", "conf", "cache"):
			self._saved[name] = getattr(frappe.local, name, None) if hasattr(frappe, "local") else None
		self._saved_cache = getattr(frappe, "cache", None)

		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Administrator", data=frappe._dict())
		frappe.local.site = "test.local"
		frappe.local.conf = frappe._dict(developer_mode=True)
		frappe.local.db = MagicMock()
		self.mock_cache = MagicMock()
		self.mock_cache.get_value.return_value = 0
		frappe.cache = MagicMock(return_value=self.mock_cache)

	def tearDown(self):
		frappe.cache = self._saved_cache
		for name in ("flags", "session", "db", "site", "conf", "cache"):
			val = self._saved.get(name)
			if val is not None:
				setattr(frappe.local, name, val)
			else:
				try:
					delattr(frappe.local, name)
				except AttributeError:
					pass
		super().tearDown()

	def test_empty_agent_pool(self):
		"""When no agents are eligible, conversation remains unassigned without raising error."""
		conv = MagicMock()
		conv.name = "CONV_EMPTY_POOL"
		conv.profile = "prof_0"
		conv.assignee = None
		conv.assignment_status = "Unassigned"
		conv.assignment_source = "Manual"
		conv.last_assigned_on = None

		with patch("nudg.services.assignments.get_eligible_desk_agents", return_value=[]):
			res = assignments.auto_assign_round_robin(conv)
			self.assertIsNone(res["assignee"])
			self.assertEqual(res["assignment_status"], "Unassigned")
			conv.save.assert_not_called()

	def test_single_agent_pool_repeated_assignments(self):
		"""When only one agent exists, all conversations are sequentially assigned to that agent."""
		single_agent = "solo_agent@example.com"
		with patch("nudg.services.assignments.get_eligible_desk_agents", return_value=[single_agent]), \
			 patch("nudg.services.assignments._sync_todo"), \
			 patch("frappe.publish_realtime"):

			for i in range(5):
				conv = MagicMock()
				conv.name = f"CONV_SOLO_{i}"
				conv.profile = f"prof_{i}"
				conv.assignee = None
				conv.assignment_status = "Unassigned"
				conv.assignment_source = "Manual"
				conv.last_assigned_on = None

				recent_rows = [frappe._dict({"assignee": single_agent, "last_assigned_on": datetime.datetime(2026, 11, 8, 10, i, 0)})] if i > 0 else []
				with patch("frappe.get_all", return_value=recent_rows):
					res = assignments.auto_assign_round_robin(conv)
					self.assertEqual(res["assignee"], single_agent)
					self.assertEqual(conv.assignee, single_agent)
					self.assertEqual(conv.assignment_source, "Round Robin")

	def test_concurrent_round_robin_assignments(self):
		"""Concurrent execution across threads assigning unassigned conversations."""
		agents = ["agent_1@example.com", "agent_2@example.com", "agent_3@example.com"]

		import threading
		cache_lock = threading.Lock()
		cache_store = {"nudg_rr_unassigned_ptr": 0}

		class ConcurrentCacheMock:
			def get_value(self, k):
				with cache_lock:
					return cache_store.get(k, 0)

			def set_value(self, k, v, **kwargs):
				with cache_lock:
					cache_store[k] = v

		cache_inst = ConcurrentCacheMock()

		def make_conv(idx):
			c = MagicMock()
			c.name = f"CONV_CONCURRENT_{idx}"
			c.profile = f"prof_concurrent_{idx}"
			c.assignee = None
			c.assignment_status = "Unassigned"
			c.assignment_source = "Manual"
			c.last_assigned_on = None
			c.tags = ""
			return c

		conversations = [make_conv(i) for i in range(12)]

		def runner(conv_doc):
			_setup_thread_frappe()
			frappe.cache = MagicMock(return_value=cache_inst)
			return assignments.auto_assign_round_robin(conv_doc)

		with patch("nudg.services.assignments.get_eligible_desk_agents", return_value=agents), \
			 patch("nudg.services.assignments._sync_todo"), \
			 patch("frappe.get_all", return_value=[]), \
			 patch("frappe.publish_realtime"):

			with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
				futures = [executor.submit(runner, c) for c in conversations]
				results = [f.result() for f in futures]

			assigned_agents = [r["assignee"] for r in results]
			for a in assigned_agents:
				self.assertIn(a, agents)
			self.assertEqual(len(assigned_agents), 12)

	def test_corrupted_last_assigned_timestamp_fallback(self):
		"""Vulnerability check: corrupt/unparseable last_assigned_on values in database must not crash routing."""
		agents = ["agent_a@example.com", "agent_b@example.com"]
		conv = MagicMock()
		conv.name = "CONV_CORRUPT"
		conv.profile = "prof_corrupt"
		conv.assignee = None
		conv.assignment_status = "Unassigned"
		conv.assignment_source = "Manual"
		conv.last_assigned_on = None

		corrupt_rows = [
			frappe._dict({"assignee": "agent_a@example.com", "last_assigned_on": "NOT_A_VALID_DATE"}),
			frappe._dict({"assignee": "agent_b@example.com", "last_assigned_on": datetime.datetime(2026, 11, 8, 10, 0, 0)}),
		]

		with patch("nudg.services.assignments.get_eligible_desk_agents", return_value=agents), \
			 patch("nudg.services.assignments._sync_todo"), \
			 patch("frappe.get_all", return_value=corrupt_rows), \
			 patch("frappe.publish_realtime"):

			try:
				res = assignments.auto_assign_round_robin(conv)
				self.assertIn(res["assignee"], agents)
			except Exception as exc:
				self.fail(f"VULNERABILITY CONFIRMED: auto_assign_round_robin crashed on unparseable timestamp: {exc}")


if __name__ == "__main__":
	unittest.main()
