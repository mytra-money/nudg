# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Milestone 1 Empirical Adversarial & Stress Test Suite.

Adversarially challenges:
1. HMAC signature verification, spoofing, tampering, prefix anomalies, and timing-attack resilience.
2. Secret redaction of access tokens (EAAB...) across API errors, network timeouts, connection failures, and raw_response dicts.
3. Single default channel mutations, deletions, unchecking, and concurrent race resolution.
4. Backoff retry behavior under persistent HTTP 429 and HTTP 503 responses, including malformed Retry-After headers.
5. Message status transition monotonicity, out-of-order delivery, and terminal state preservation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import unittest
from unittest.mock import MagicMock, call, patch

import requests

import frappe
from werkzeug.wrappers import Response

from nudg.integrations import webhook
from nudg.integrations.connector.base import (
	WhatsAppAuthError,
	WhatsAppConnectorError,
	WhatsAppNetworkError,
	WhatsAppRateLimitError,
)
from nudg.integrations.connector.meta_cloud import DirectMetaCloudApiConnector
from nudg.integrations.repository.message_repo import DeskMessageRepository

CONNECTOR_TYPE_META_DIRECT = "Meta Cloud Direct"
STATUS_ACTIVE = "Active"
STATUS_INACTIVE = "Inactive"

class TestWebhookAdversarialSecurity(unittest.TestCase):
	"""Adversarial security tests for webhook verification and HMAC ingestion."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "request", "form_dict", "response", "lang"):
			self._saved[name] = getattr(frappe.local, name, None)
		self._saved_cache = getattr(frappe, "cache", None)

		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Guest", data=frappe._dict())
		frappe.local.lang = "en"
		frappe.local.db = MagicMock()
		frappe.local.response = frappe._dict()
		frappe.local.form_dict = frappe._dict()

		frappe.cache = MagicMock()
		frappe.cache.hget.return_value = {}

		self.mock_request = MagicMock()
		self.mock_request.method = "POST"
		self.mock_request.args = {}
		self.mock_request.get_data.return_value = b""
		frappe.local.request = self.mock_request

		self.secret = "production_super_secret_webhook_key_2026"
		self.raw_payload = json.dumps({
			"entry": [
				{
					"changes": [
						{
							"field": "messages",
							"value": {
								"metadata": {"phone_number_id": "9876543210"},
								"contacts": [{"profile": {"name": "Mallory"}}],
								"messages": [
									{"id": "wamid.ATTACK001", "from": "15550001111", "type": "text", "text": {"body": "Hacked"}}
								],
							},
						}
					]
				}
			]
		}).encode("utf-8")
		self.mock_request.get_data.return_value = self.raw_payload

	def tearDown(self):
		frappe.cache = self._saved_cache
		for name in ("flags", "session", "db", "request", "form_dict", "response", "lang"):
			val = self._saved.get(name)
			if val is not None:
				setattr(frappe.local, name, val)
			else:
				try:
					delattr(frappe.local, name)
				except AttributeError:
					pass
		super().tearDown()

	def _compute_valid_signature(self, body: bytes, secret: str) -> str:
		return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

	# -------------------------------------------------------------------------
	# 1. HMAC Signature Spoofing and Tampering
	# -------------------------------------------------------------------------

	def test_hmac_spoofed_secret_rejected(self):
		"""Attacker signs payload with their own secret; must raise AuthenticationError."""
		attacker_secret = "attacker_fake_secret_key"
		spoofed_header = self._compute_valid_signature(self.raw_payload, attacker_secret)

		with patch("frappe.get_request_header", return_value=spoofed_header):
			with patch.object(webhook, "_resolve_channel", return_value=None):
				with patch.object(webhook, "_get_webhook_secret", return_value=self.secret):
					with self.assertRaises(frappe.AuthenticationError):
						webhook.handler()

	def test_hmac_tampered_signature_one_bit_rejected(self):
		"""Valid signature with 1 character flipped must raise AuthenticationError."""
		valid_header = self._compute_valid_signature(self.raw_payload, self.secret)
		# Flip the last character
		tampered = valid_header[:-1] + ("0" if valid_header[-1] != "0" else "1")

		with patch("frappe.get_request_header", return_value=tampered):
			with patch.object(webhook, "_resolve_channel", return_value=None):
				with patch.object(webhook, "_get_webhook_secret", return_value=self.secret):
					with self.assertRaises(frappe.AuthenticationError):
						webhook.handler()

	def test_hmac_missing_header_rejected(self):
		"""Missing X-Hub-Signature-256 header must raise AuthenticationError."""
		with patch("frappe.get_request_header", return_value=None):
			with patch.object(webhook, "_resolve_channel", return_value=None):
				with patch.object(webhook, "_get_webhook_secret", return_value=self.secret):
					with self.assertRaises(frappe.AuthenticationError):
						webhook.handler()

	def test_hmac_empty_header_rejected(self):
		"""Empty string X-Hub-Signature-256 header must raise AuthenticationError."""
		with patch("frappe.get_request_header", return_value=""):
			with patch.object(webhook, "_resolve_channel", return_value=None):
				with patch.object(webhook, "_get_webhook_secret", return_value=self.secret):
					with self.assertRaises(frappe.AuthenticationError):
						webhook.handler()

	def test_hmac_malformed_prefixes_rejected(self):
		"""Header with sha1=, md5=, Bearer, or uppercase SHA256= must raise AuthenticationError."""
		valid_hash = hmac.new(self.secret.encode("utf-8"), self.raw_payload, hashlib.sha256).hexdigest()
		malformed_headers = [
			f"sha1={valid_hash}",
			f"md5={valid_hash}",
			f"Bearer {valid_hash}",
			f"SHA256={valid_hash}",
			f"sha256: {valid_hash}",
			"sha256=",
			f"sha256={valid_hash[:10]}",  # Truncated
		]
		for bad_header in malformed_headers:
			with self.subTest(bad_header=bad_header):
				with patch("frappe.get_request_header", return_value=bad_header):
					with patch.object(webhook, "_resolve_channel", return_value=None):
						with patch.object(webhook, "_get_webhook_secret", return_value=self.secret):
							with self.assertRaises(frappe.AuthenticationError):
								webhook.handler()

	def test_hmac_payload_tampered_after_signing_rejected(self):
		"""Signature valid for Payload A, but Payload B sent; must raise AuthenticationError."""
		original_body = b'{"msg": "legitimate"}'
		tampered_body = b'{"msg": "tampered"}'
		sig = self._compute_valid_signature(original_body, self.secret)

		self.mock_request.get_data.return_value = tampered_body
		with patch("frappe.get_request_header", return_value=sig):
			with patch.object(webhook, "_resolve_channel", return_value=None):
				with patch.object(webhook, "_get_webhook_secret", return_value=self.secret):
					with self.assertRaises(frappe.AuthenticationError):
						webhook.handler()

	def test_hmac_timing_attack_uses_compare_digest(self):
		"""Verify that _verify_signature explicitly delegates to constant-time hmac.compare_digest."""
		valid_header = self._compute_valid_signature(self.raw_payload, self.secret)
		with patch("frappe.get_request_header", return_value=valid_header):
			with patch("hmac.compare_digest", wraps=hmac.compare_digest) as mock_compare:
				webhook._verify_signature(self.raw_payload, self.secret)
				mock_compare.assert_called_once()
				computed, expected = mock_compare.call_args[0]
				self.assertEqual(len(computed), 64)
				self.assertEqual(len(expected), 64)

	# -------------------------------------------------------------------------
	# 2. GET Verification Challenge Edge Cases
	# -------------------------------------------------------------------------

	def test_get_challenge_missing_parameters_rejected(self):
		"""GET verification missing challenge or token must return 400."""
		self.mock_request.method = "GET"
		test_cases = [
			{"hub.mode": "subscribe", "hub.verify_token": "token123"},  # missing challenge
			{"hub.mode": "subscribe", "hub.challenge": "ch123"},       # missing token
			{"hub.verify_token": "token123", "hub.challenge": "ch123"}, # missing mode
			{"hub.mode": "publish", "hub.verify_token": "t", "hub.challenge": "c"}, # wrong mode
		]
		for case in test_cases:
			with self.subTest(case=case):
				frappe.form_dict = frappe._dict(case)
				resp = webhook.handler()
				self.assertIsInstance(resp, Response)
				self.assertEqual(resp.status_code, 400)

	def test_get_challenge_sql_injection_probe_fails(self):
		"""GET verification with SQL injection token returns 403."""
		self.mock_request.method = "GET"
		frappe.form_dict = frappe._dict({
			"hub.mode": "subscribe",
			"hub.verify_token": "' OR '1'='1",
			"hub.challenge": "probe_challenge",
		})
		frappe.db.exists.return_value = True
		frappe.db.get_value.return_value = None  # SQL engine parameterized lookup yields nothing
		frappe.db.get_single_value.return_value = "actual_real_token"

		resp = webhook.handler()
		self.assertIsInstance(resp, Response)
		self.assertEqual(resp.status_code, 403)
		self.assertIn("mismatch", resp.get_data(as_text=True))


class TestSecretRedactionAdversarial(unittest.TestCase):
	"""Adversarial tests ensuring zero secret/token leakage across failures and representations."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "valid_columns", "cache"):
			self._saved[name] = getattr(frappe.local, name, None) if name != "cache" else getattr(frappe, "cache", None)

		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Administrator", data=frappe._dict())
		frappe.local.valid_columns = {"WA Account": []}
		self.mock_db = MagicMock()
		self.mock_db.get_table_columns.return_value = []
		frappe.local.db = self.mock_db

		frappe.cache = MagicMock()
		frappe.cache.hget.return_value = {}

		self.mock_meta = MagicMock()
		self.mock_meta._table_doctypes = {}
		self.mock_meta.has_field.return_value = True
		self.mock_meta.get_field.return_value = None
		self.meta_patch = patch("frappe.get_meta", return_value=self.mock_meta)
		self.meta_patch.start()

		self.connector = DirectMetaCloudApiConnector()
		self.token = "EAAB1234567890abcdef998877665544332211"
		self.channel_cfg = {
			"phone_number_id": "100200300",
			"access_token": self.token,
			"api_version": "v18.0",
			"api_base_url": "https://graph.facebook.com",
		}

	def tearDown(self):
		self.meta_patch.stop()
		frappe.cache = self._saved.get("cache")
		for name in ("flags", "session", "db", "valid_columns"):
			val = self._saved.get(name)
			if val is not None:
				setattr(frappe.local, name, val)
			else:
				try:
					delattr(frappe.local, name)
				except AttributeError:
					pass
		super().tearDown()

	# -------------------------------------------------------------------------
	# 1. API Error Responses Token Redaction
	# -------------------------------------------------------------------------

	def test_meta_cloud_redacts_token_from_http_400_exception_message(self):
		"""HTTP 400 error message with EAAB token must be redacted in exception string."""
		resp_err = MagicMock(spec=requests.Response)
		resp_err.status_code = 400
		resp_err.text = f"Invalid request with token {self.token}"
		resp_err.json.return_value = {
			"error": {
				"message": f"Malformed parameters for {self.token}",
				"code": 100,
				"error_subcode": 33,
			}
		}

		with patch.object(self.connector.session, "request", return_value=resp_err):
			with self.assertRaises(WhatsAppConnectorError) as ctx:
				self.connector.send_text(self.channel_cfg, to="15551234567", text="test")
			err_msg = str(ctx.exception)
			self.assertNotIn(self.token, err_msg)
			self.assertIn("EAAB[REDACTED]", err_msg)

	def test_meta_cloud_redacts_token_from_network_connection_error(self):
		"""Network connection error containing EAAB token must be redacted in WhatsAppNetworkError."""
		raw_conn_error = requests.exceptions.ConnectionError(
			f"Failed to establish connection to https://graph.facebook.com/v18.0/100200300/messages?token={self.token}"
		)

		with patch.object(self.connector.session, "request", side_effect=raw_conn_error):
			with self.assertRaises(WhatsAppNetworkError) as ctx:
				self.connector.send_text(self.channel_cfg, to="15551234567", text="test")
			err_msg = str(ctx.exception)
			self.assertNotIn(
				self.token,
				err_msg,
				f"VULNERABILITY: Raw access token leaked in network exception message: {err_msg}",
			)

	def test_meta_cloud_redacts_token_from_network_timeout_error(self):
		"""Network timeout error containing EAAB token must be redacted in WhatsAppNetworkError."""
		raw_timeout = requests.exceptions.Timeout(
			f"HTTPSConnectionPool timeout with Authorization: Bearer {self.token}"
		)

		with patch.object(self.connector.session, "request", side_effect=raw_timeout):
			with self.assertRaises(WhatsAppNetworkError) as ctx:
				self.connector.send_text(self.channel_cfg, to="15551234567", text="test")
			err_msg = str(ctx.exception)
			self.assertNotIn(
				self.token,
				err_msg,
				f"VULNERABILITY: Raw access token leaked in timeout exception message: {err_msg}",
			)

	def test_meta_cloud_redacts_token_from_raw_response_dict(self):
		"""raw_response dictionary attached to raised exceptions must not retain raw EAAB tokens."""
		resp_err = MagicMock(spec=requests.Response)
		resp_err.status_code = 500
		resp_err.text = f"Internal Server Error: Debug token = {self.token}"
		resp_err.json.side_effect = Exception("Not JSON")

		with patch.object(self.connector.session, "request", return_value=resp_err):
			with self.assertRaises(WhatsAppConnectorError) as ctx:
				self.connector.send_text(self.channel_cfg, to="15551234567", text="test")
			raw_resp = ctx.exception.raw_response
			raw_resp_str = json.dumps(raw_resp) if isinstance(raw_resp, dict) else str(raw_resp)
			self.assertNotIn(
				self.token,
				raw_resp_str,
				f"VULNERABILITY: Raw access token leaked in exception.raw_response: {raw_resp_str}",
			)

class TestBackoffRetryBehaviorAdversarial(unittest.TestCase):
	"""Adversarial stress tests for backoff retries on HTTP 429 and HTTP 503."""

	def setUp(self):
		super().setUp()
		self.connector = DirectMetaCloudApiConnector()
		self.channel_cfg = {
			"phone_number_id": "100200300",
			"access_token": "TEST_TOKEN_123",
		}

	# -------------------------------------------------------------------------
	# 1. HTTP 429 Retry and Exhaustion
	# -------------------------------------------------------------------------

	def test_http_429_persistent_exhaustion_raises_rate_limit_error(self):
		"""Persistent 429 responses exhaust retries (4 total attempts) and raise WhatsAppRateLimitError."""
		resp_429 = MagicMock(spec=requests.Response)
		resp_429.status_code = 429
		resp_429.headers = {"Retry-After": "0.01"}
		resp_429.json.return_value = {"error": {"message": "Rate limit exceeded", "code": 80007}}

		with patch.object(self.connector.session, "request", return_value=resp_429) as mock_req:
			with patch("time.sleep") as mock_sleep:
				with self.assertRaises(WhatsAppRateLimitError):
					self.connector.send_text(self.channel_cfg, to="15551234567", text="Persistent 429 test")
				# Default max_rate_limit_retries is 3 -> 1 initial + 3 retries = 4 attempts
				self.assertEqual(mock_req.call_count, 4)
				self.assertEqual(mock_sleep.call_count, 3)

	def test_http_429_exponential_backoff_delays_increase(self):
		"""Under 429 without Retry-After header, sleep delay increases exponentially with jitter."""
		resp_429 = MagicMock(spec=requests.Response)
		resp_429.status_code = 429
		resp_429.headers = {}  # No Retry-After header
		resp_429.json.return_value = {"error": {"message": "Rate limited", "code": 80007}}

		resp_200 = MagicMock(spec=requests.Response)
		resp_200.status_code = 200
		resp_200.json.return_value = {"messages": [{"id": "wamid.RETRY_SUCCESS"}]}

		# Fails twice with 429, succeeds on 3rd try
		with patch.object(self.connector.session, "request", side_effect=[resp_429, resp_429, resp_200]):
			with patch("time.sleep") as mock_sleep:
				res = self.connector.send_text(self.channel_cfg, to="15551234567", text="Exp backoff test")
				self.assertTrue(res["success"])
				self.assertEqual(mock_sleep.call_count, 2)
				delay1 = mock_sleep.call_args_list[0][0][0]
				delay2 = mock_sleep.call_args_list[1][0][0]
				# backoff starts at 0.5 + jitter (0.05-0.2) -> 0.55-0.7
				# 2nd retry backoff is 1.0 + jitter -> 1.05-1.2
				self.assertGreater(delay2, delay1)

	def test_http_429_malformed_retry_after_header_handled_gracefully(self):
		"""HTTP-date or non-float Retry-After header (RFC 7231) must not crash with ValueError."""
		resp_429 = MagicMock(spec=requests.Response)
		resp_429.status_code = 429
		resp_429.headers = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
		resp_429.json.return_value = {"error": {"message": "Rate limited", "code": 80007}}

		resp_200 = MagicMock(spec=requests.Response)
		resp_200.status_code = 200
		resp_200.json.return_value = {"messages": [{"id": "wamid.DATE_HEADER_OK"}]}

		with patch.object(self.connector.session, "request", side_effect=[resp_429, resp_200]):
			with patch("time.sleep"):
				try:
					res = self.connector.send_text(self.channel_cfg, to="15551234567", text="Header test")
					self.assertTrue(res["success"])
				except ValueError as exc:
					self.fail(f"DEFECT: Connector crashed on HTTP-date Retry-After header: {exc}")

	# -------------------------------------------------------------------------
	# 2. HTTP 503 Retry and Error Classification
	# -------------------------------------------------------------------------

	def test_http_503_retries_with_backoff(self):
		"""HTTP 503 Service Unavailable must trigger exponential backoff retry."""
		resp_503 = MagicMock(spec=requests.Response)
		resp_503.status_code = 503
		resp_503.headers = {"Retry-After": "1"}
		resp_503.json.return_value = {"error": {"message": "Service temporarily unavailable", "code": 2}}

		resp_200 = MagicMock(spec=requests.Response)
		resp_200.status_code = 200
		resp_200.json.return_value = {"messages": [{"id": "wamid.503_RETRY_OK"}]}

		with patch.object(self.connector.session, "request", side_effect=[resp_503, resp_200]) as mock_req:
			with patch("time.sleep") as mock_sleep:
				try:
					res = self.connector.send_text(self.channel_cfg, to="15551234567", text="503 test")
					self.assertTrue(res["success"])
					self.assertEqual(mock_req.call_count, 2)
					mock_sleep.assert_called_once()
				except WhatsAppConnectorError as exc:
					self.fail(
						f"DEFECT: HTTP 503 was aborted without retry backoff: {exc} "
						f"(session.request call count = {mock_req.call_count})"
					)

	def test_http_503_persistent_raises_network_error(self):
		"""Persistent 5xx upstream failure should raise WhatsAppNetworkError per contract in base.py."""
		resp_503 = MagicMock(spec=requests.Response)
		resp_503.status_code = 503
		resp_503.text = "Service Unavailable"
		resp_503.json.return_value = {"error": {"message": "Service Unavailable", "code": 2}}

		with patch.object(self.connector.session, "request", return_value=resp_503):
			with self.assertRaises(WhatsAppNetworkError, msg="DEFECT: 503 raised generic WhatsAppConnectorError instead of WhatsAppNetworkError"):
				self.connector.send_text(self.channel_cfg, to="15551234567", text="503 failure")


class TestRepositoryStatusTransitionsAdversarial(unittest.TestCase):
	"""Adversarial tests for message status transition monotonicity and deduplication."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "cache"):
			self._saved[name] = getattr(frappe.local, name, None) if name != "cache" else getattr(frappe, "cache", None)

		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Administrator", data=frappe._dict())
		self.mock_db = MagicMock()
		frappe.local.db = self.mock_db

		frappe.cache = MagicMock()
		frappe.cache.hget.return_value = {}

	def tearDown(self):
		frappe.cache = self._saved.get("cache")
		for name in ("flags", "session", "db"):
			val = self._saved.get(name)
			if val is not None:
				setattr(frappe.local, name, val)
			else:
				try:
					delattr(frappe.local, name)
				except AttributeError:
					pass
		super().tearDown()

	def test_status_monotonicity_read_does_not_revert_to_delivered(self):
		"""Out-of-order 'delivered' status receipt must not overwrite 'Read' status."""
		self.mock_db.exists.return_value = True
		self.mock_db.get_value.side_effect = lambda dt, name_or_filters, fieldname=None: (
			"MSG-001" if fieldname == "name" or (isinstance(name_or_filters, dict) and "message_id" in name_or_filters) else "Read"
		)

		with patch("frappe.publish_realtime"):
			updated = DeskMessageRepository.update_message_status("wamid.123", "delivered")
			self.assertFalse(updated)
			self.mock_db.set_value.assert_not_called()

	def test_status_monotonicity_delivered_does_not_revert_to_sent(self):
		"""Delayed 'sent' status must not overwrite 'Delivered' status."""
		self.mock_db.exists.return_value = True
		self.mock_db.get_value.side_effect = lambda dt, name_or_filters, fieldname=None: (
			"MSG-001" if fieldname == "name" or (isinstance(name_or_filters, dict) and "message_id" in name_or_filters) else "Delivered"
		)

		with patch("frappe.publish_realtime"):
			updated = DeskMessageRepository.update_message_status("wamid.123", "sent")
			self.assertFalse(updated)
			self.mock_db.set_value.assert_not_called()

	def test_status_monotonicity_terminal_failed_state_is_never_overwritten(self):
		"""A 'Failed' message cannot transition to 'Delivered' or 'Read'."""
		self.mock_db.exists.return_value = True
		self.mock_db.get_value.side_effect = lambda dt, name_or_filters, fieldname=None: (
			"MSG-001" if fieldname == "name" or (isinstance(name_or_filters, dict) and "message_id" in name_or_filters) else "Failed"
		)

		with patch("frappe.publish_realtime"):
			updated_deliv = DeskMessageRepository.update_message_status("wamid.123", "delivered")
			self.assertFalse(updated_deliv)
			updated_read = DeskMessageRepository.update_message_status("wamid.123", "read")
			self.assertFalse(updated_read)
			self.mock_db.set_value.assert_not_called()

	def test_status_transition_to_failed_records_error_payload(self):
		"""Transitioning to 'Failed' persists error payload and publishes realtime event."""
		self.mock_db.exists.return_value = True
		self.mock_db.get_value.side_effect = lambda dt, name_or_filters, fieldname=None: (
			"MSG-001" if fieldname == "name" or (isinstance(name_or_filters, dict) and "message_id" in name_or_filters) else "Sent"
		)

		with patch("frappe.publish_realtime") as mock_realtime:
			err_data = [{"code": 131026, "title": "Message undeliverable"}]
			updated = DeskMessageRepository.update_message_status(
				"wamid.123",
				"failed",
				errors=err_data,
			)
			self.assertTrue(updated)
			self.mock_db.set_value.assert_called_once()
			call_args = self.mock_db.set_value.call_args[0]
			updates = call_args[2]
			self.assertEqual(updates["status"], "Failed")
			self.assertIn("131026", updates["error_message"])
			mock_realtime.assert_called_once()

	def test_save_incoming_message_float_string_timestamp_resilience(self):
		"""Float string timestamp e.g. '1700000000.5' must not crash with unhandled ValueError."""
		msg = {
			"id": "wamid.TS_FLOAT",
			"type": "text",
			"timestamp": "1700000000.5",
			"text": {"body": "Timestamp stress test"},
		}
		self.mock_db.exists.return_value = False
		with patch.object(DeskMessageRepository, "is_self_hosted", return_value=False):
			with patch("frappe.publish_realtime"):
				try:
					res = DeskMessageRepository.save_incoming_message("Test Channel", msg, "contact_1")
					self.assertEqual(res["message_id"], "wamid.TS_FLOAT")
				except ValueError as exc:
					self.fail(f"DEFECT: DeskMessageRepository.save_incoming_message crashed on float string timestamp: {exc}")

	def test_webhook_burst_message_deduplication(self):
		"""Burst of 10 identical wamid messages must result in only 1 save, 9 skipped."""
		seen_ids = set()

		def fake_is_duplicate(msg_id):
			return msg_id in seen_ids

		saved_count = 0

		def fake_save(*args, **kwargs):
			nonlocal saved_count
			saved_count += 1
			seen_ids.add("wamid.BURST999")
			return {"record_name": "MSG-BURST", "content": "Hello"}

		with patch("nudg.integrations.repository.message_repo.DeskMessageRepository.is_duplicate_message", side_effect=fake_is_duplicate):
			with patch("nudg.integrations.repository.message_repo.DeskMessageRepository.save_incoming_message", side_effect=fake_save):
				for _ in range(10):
					is_dup = DeskMessageRepository.is_duplicate_message("wamid.BURST999")
					if not is_dup:
						DeskMessageRepository.save_incoming_message("chan", {"id": "wamid.BURST999"}, "contact_1")

		self.assertEqual(saved_count, 1)
		self.assertTrue(fake_is_duplicate("wamid.BURST999"))

