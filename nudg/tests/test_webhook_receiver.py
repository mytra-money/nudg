# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

from __future__ import annotations

import hashlib
import hmac
import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from werkzeug.wrappers import Response

from nudg.integrations import webhook


class TestWebhookReceiver(unittest.TestCase):
	"""Unit tests verifying webhook GET challenge verification and POST HMAC ingestion."""

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

		# Default mock request
		self.mock_request = MagicMock()
		self.mock_request.method = "GET"
		self.mock_request.args = {}
		self.mock_request.get_data.return_value = b""
		frappe.local.request = self.mock_request

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

	# -------------------------------------------------------------------------
	# 1. GET Challenge Verification Tests
	# -------------------------------------------------------------------------

	def test_get_challenge_verification_success(self):
		"""GET with valid hub.mode and verify_token returns raw challenge text/plain."""
		frappe.form_dict = frappe._dict({
			"hub.mode": "subscribe",
			"hub.verify_token": "correct_token_123",
			"hub.challenge": "1155993388",
		})
		frappe.local.request.method = "GET"

		frappe.db.exists.side_effect = lambda dt, filters=None: dt in ("DocType", "WA Settings")
		frappe.db.get_single_value.return_value = "correct_token_123"

		resp = webhook.handler()
		self.assertIsInstance(resp, Response)
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.mimetype, "text/plain")
		self.assertEqual(resp.get_data(as_text=True), "1155993388")

	def test_get_challenge_verification_token_mismatch(self):
		"""GET with incorrect verify token returns 403."""
		frappe.form_dict = frappe._dict({
			"hub.mode": "subscribe",
			"hub.verify_token": "wrong_token",
			"hub.challenge": "1155993388",
		})
		frappe.local.request.method = "GET"

		frappe.db.exists.return_value = True
		frappe.db.get_value.return_value = None  # No channel matches
		frappe.db.get_single_value.return_value = "correct_token_123"

		resp = webhook.handler()
		self.assertIsInstance(resp, Response)
		self.assertEqual(resp.status_code, 403)
		self.assertIn("mismatch", resp.get_data(as_text=True))

	def test_get_challenge_invalid_mode(self):
		"""GET with invalid mode returns 400."""
		frappe.form_dict = frappe._dict({
			"hub.mode": "invalid_mode",
			"hub.verify_token": "correct_token_123",
			"hub.challenge": "1155993388",
		})
		frappe.local.request.method = "GET"

		resp = webhook.handler()
		self.assertIsInstance(resp, Response)
		self.assertEqual(resp.status_code, 400)

	# -------------------------------------------------------------------------
	# 2. POST HMAC Signature Verification Tests
	# -------------------------------------------------------------------------

	def test_post_signature_mismatch_throws_auth_error(self):
		"""POST with invalid HMAC signature throws AuthenticationError."""
		secret = "my_app_secret"
		payload = json.dumps({"entry": []}).encode("utf-8")

		frappe.local.request.method = "POST"
		frappe.local.request.get_data.return_value = payload

		with patch("frappe.get_request_header", return_value="sha256=invalidhash12345"):
			with patch.object(webhook, "_resolve_channel", return_value=None):
				with patch.object(webhook, "_get_webhook_secret", return_value=secret):
					with self.assertRaises(frappe.AuthenticationError):
						webhook.handler()

	def test_post_signature_valid(self):
		"""POST with valid HMAC signature succeeds."""
		secret = "my_app_secret"
		payload = json.dumps({"entry": []}).encode("utf-8")
		valid_hash = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

		frappe.local.request.method = "POST"
		frappe.local.request.get_data.return_value = payload

		with patch("frappe.get_request_header", return_value=f"sha256={valid_hash}"):
			with patch.object(webhook, "_resolve_channel", return_value=None):
				with patch.object(webhook, "_get_webhook_secret", return_value=secret):
					resp = webhook.handler()
					self.assertEqual(resp, "ok")

	# -------------------------------------------------------------------------
	# 3. Message Ingestion & Deduplication Tests
	# -------------------------------------------------------------------------

	def test_post_message_deduplication(self):
		"""Duplicate message ID is skipped without re-saving."""
		raw_event = {
			"entry": [
				{
					"changes": [
						{
							"field": "messages",
							"value": {
								"metadata": {"phone_number_id": "100200"},
								"contacts": [{"profile": {"name": "Bob"}}],
								"messages": [
									{"id": "wamid.DUPLICATE123", "from": "15551234567", "type": "text", "text": {"body": "Hi"}}
								],
							},
						}
					]
				}
			]
		}
		raw_bytes = json.dumps(raw_event).encode("utf-8")
		frappe.local.request.method = "POST"
		frappe.local.request.get_data.return_value = raw_bytes

		with patch.object(webhook, "_resolve_channel", return_value=None):
			with patch.object(webhook, "_get_webhook_secret", return_value=None):
				with patch("nudg.integrations.repository.message_repo.DeskMessageRepository.is_duplicate_message", return_value=True):
					with patch("nudg.integrations.repository.message_repo.DeskMessageRepository.save_incoming_message") as mock_save:
						resp = webhook.handler()
						self.assertEqual(resp, "ok")
						mock_save.assert_not_called()

	def test_post_message_ingestion_and_stop_keyword(self):
		"""Inbound message with 'STOP' triggers consent opt-out."""
		raw_event = {
			"entry": [
				{
					"changes": [
						{
							"field": "messages",
							"value": {
								"metadata": {"phone_number_id": "100200"},
								"contacts": [{"profile": {"name": "Alice"}}],
								"messages": [
									{"id": "wamid.STOP123", "from": "15559998888", "type": "text", "text": {"body": "STOP"}}
								],
							},
						}
					]
				}
			]
		}
		raw_bytes = json.dumps(raw_event).encode("utf-8")
		frappe.local.request.method = "POST"
		frappe.local.request.get_data.return_value = raw_bytes

		with patch.object(webhook, "_resolve_channel", return_value=None):
			with patch.object(webhook, "_get_webhook_secret", return_value=None):
				with patch("nudg.integrations.repository.message_repo.DeskMessageRepository.is_duplicate_message", return_value=False):
					with patch("nudg.integrations.repository.contact_repo.DeskContactRepository.get_or_create_contact", return_value="Alice-Contact"):
						with patch("nudg.integrations.repository.message_repo.DeskMessageRepository.save_incoming_message", return_value={"record_name": "MSG-99", "content": "STOP"}):
							with patch("nudg.integrations.repository.contact_repo.DeskContactRepository.update_consent") as mock_consent:
								with patch.object(webhook, "_trigger_automations") as mock_auto:
									resp = webhook.handler()
									self.assertEqual(resp, "ok")
									mock_consent.assert_called_once_with("Alice-Contact", "Opted-Out", reason="STOP keyword")
									mock_auto.assert_called_once_with("Alice-Contact", "", "MSG-99")

	def test_post_status_update_delivered(self):
		"""Incoming status update updates message status in repository."""
		raw_event = {
			"entry": [
				{
					"changes": [
						{
							"field": "messages",
							"value": {
								"metadata": {"phone_number_id": "100200"},
								"statuses": [
									{"id": "wamid.OUTBOUND123", "status": "delivered", "timestamp": "1700000000"}
								],
							},
						}
					]
				}
			]
		}
		raw_bytes = json.dumps(raw_event).encode("utf-8")
		frappe.local.request.method = "POST"
		frappe.local.request.get_data.return_value = raw_bytes

		with patch.object(webhook, "_resolve_channel", return_value=None):
			with patch.object(webhook, "_get_webhook_secret", return_value=None):
				with patch("nudg.integrations.repository.message_repo.DeskMessageRepository.update_message_status") as mock_status:
					resp = webhook.handler()
					self.assertEqual(resp, "ok")
					mock_status.assert_called_once_with(
						message_id="wamid.OUTBOUND123",
					new_status_raw="delivered",
					timestamp="1700000000",
					errors=None,
				)
