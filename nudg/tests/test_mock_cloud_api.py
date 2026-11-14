# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

"""Automated Unit and Integration Test Suite using MockWhatsAppCloudApi.

Covers Requirement R4:
1. Outbound DirectMetaCloudApiConnector testing against MockWhatsAppCloudApi:
   - send_text, send_template, send_media, send_interactive (SPM & MPM), mark_as_read
   - Retry & exponential backoff on HTTP 429 and HTTP 503 with Retry-After header
   - Token scrubbing and secret sanitization on simulated 401 error
   - Payload schema validation and bad request rejection
2. Inbound Webhook Testing:
   - HMAC-SHA256 signature verification (valid header vs. signature mismatch)
   - Inbound text message ingestion and DeskContactRepository resolution
   - Inbound order cart webhook parsing and markdown summary generation
   - STOP keyword consent interception and away message suppression
   - Status update delivery progression (Sent -> Delivered -> Read) and precedence guard
3. Campaign End-to-End Flow:
   - Run campaign through DirectMetaCloudApiConnector backed by MockWhatsAppCloudApi
   - Realtime funnel tracking assertions (sent_count, delivered_count, read_count)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest
from unittest.mock import MagicMock, patch
import uuid

import frappe
from werkzeug.wrappers import Response

from nudg.integrations import webhook
from nudg.integrations.connector.base import (
	WhatsAppAuthError,
	WhatsAppConnectorError,
	WhatsAppPayloadError,
	WhatsAppRateLimitError,
)
from nudg.integrations.connector.meta_cloud import DirectMetaCloudApiConnector
from nudg.integrations.repository.contact_repo import DeskContactRepository
from nudg.integrations.repository.message_repo import DeskMessageRepository
from nudg.services import automation, campaigns, catalog, consent
from nudg.services.catalog import build_mpm_payload, build_spm_payload
from nudg.tests.mock_cloud_api import MockWhatsAppCloudApi


class TestMockWhatsAppCloudApiHarness(unittest.TestCase):
	"""1. Direct unit tests verifying the MockWhatsAppCloudApi harness itself."""

	def setUp(self):
		super().setUp()
		self.mock_api = MockWhatsAppCloudApi(default_phone_number_id="100200300")

	def tearDown(self):
		self.mock_api.stop()
		super().tearDown()

	def test_context_manager_lifecycle(self):
		"""MockWhatsAppCloudApi starts and stops cleanly via context manager."""
		self.assertFalse(self.mock_api._is_active)
		with self.mock_api as api:
			self.assertTrue(api._is_active)
		self.assertFalse(self.mock_api._is_active)

	def test_adapter_mounting(self):
		"""MockWhatsAppCloudApiAdapter can be mounted on requests.Session."""
		import requests
		session = requests.Session()
		adapter = self.mock_api.get_adapter()
		session.mount("https://graph.facebook.com", adapter)

		headers = {"Authorization": "Bearer TEST_TOKEN"}
		payload = {
			"messaging_product": "whatsapp",
			"to": "15551234567",
			"type": "text",
			"text": {"body": "Adapter test"},
		}
		resp = session.post("https://graph.facebook.com/v18.0/100200300/messages", headers=headers, json=payload)
		self.assertEqual(resp.status_code, 200)
		data = resp.json()
		self.assertEqual(data["messaging_product"], "whatsapp")
		self.assertTrue(data["messages"][0]["id"].startswith("wamid."))

	def test_authorization_header_validation_missing(self):
		"""Request without Authorization header returns HTTP 401 code 190."""
		resp = self.mock_api.dispatch_request(
			method="POST",
			url="https://graph.facebook.com/v18.0/100200300/messages",
			headers={},
			json_data={"messaging_product": "whatsapp", "to": "15551234567", "type": "text", "text": {"body": "Hi"}},
		)
		self.assertEqual(resp.status_code, 401)
		err = resp.json().get("error", {})
		self.assertEqual(err.get("code"), 190)

	def test_authorization_header_validation_invalid_token(self):
		"""Request with INVALID_TOKEN returns HTTP 401 code 190."""
		resp = self.mock_api.dispatch_request(
			method="POST",
			url="https://graph.facebook.com/v18.0/100200300/messages",
			headers={"Authorization": "Bearer INVALID_TOKEN"},
			json_data={"messaging_product": "whatsapp", "to": "15551234567", "type": "text", "text": {"body": "Hi"}},
		)
		self.assertEqual(resp.status_code, 401)
		err = resp.json().get("error", {})
		self.assertEqual(err.get("code"), 190)

	def test_payload_validation_missing_messaging_product(self):
		"""Request missing messaging_product returns HTTP 400."""
		resp = self.mock_api.dispatch_request(
			method="POST",
			url="https://graph.facebook.com/v18.0/100200300/messages",
			headers={"Authorization": "Bearer VALID_TOKEN"},
			json_data={"to": "15551234567", "type": "text", "text": {"body": "Hi"}},
		)
		self.assertEqual(resp.status_code, 400)
		self.assertIn("messaging_product", resp.json()["error"]["message"])

	def test_payload_validation_empty_text_body(self):
		"""Text payload with empty body returns HTTP 400."""
		resp = self.mock_api.dispatch_request(
			method="POST",
			url="https://graph.facebook.com/v18.0/100200300/messages",
			headers={"Authorization": "Bearer VALID_TOKEN"},
			json_data={"messaging_product": "whatsapp", "to": "15551234567", "type": "text", "text": {"body": "   "}},
		)
		self.assertEqual(resp.status_code, 400)
		self.assertIn("empty", resp.json()["error"]["message"])

	def test_payload_validation_template_missing_language(self):
		"""Template payload missing language returns HTTP 400."""
		resp = self.mock_api.dispatch_request(
			method="POST",
			url="https://graph.facebook.com/v18.0/100200300/messages",
			headers={"Authorization": "Bearer VALID_TOKEN"},
			json_data={
				"messaging_product": "whatsapp",
				"to": "15551234567",
				"type": "template",
				"template": {"name": "sample_template"},
			},
		)
		self.assertEqual(resp.status_code, 400)
		self.assertIn("language", resp.json()["error"]["message"])

	def test_payload_validation_spm_missing_product_retailer_id(self):
		"""Single-product interactive message missing product_retailer_id returns HTTP 400."""
		resp = self.mock_api.dispatch_request(
			method="POST",
			url="https://graph.facebook.com/v18.0/100200300/messages",
			headers={"Authorization": "Bearer VALID_TOKEN"},
			json_data={
				"messaging_product": "whatsapp",
				"to": "15551234567",
				"type": "interactive",
				"interactive": {
					"type": "product",
					"action": {"catalog_id": "CATALOG_1"},
				},
			},
		)
		self.assertEqual(resp.status_code, 400)
		self.assertIn("product_retailer_id", resp.json()["error"]["message"])

	def test_payload_validation_mpm_too_many_sections(self):
		"""Multi-product interactive message with >10 sections returns HTTP 400."""
		sections = [{"title": f"Sec {i}", "product_items": [{"product_retailer_id": f"P{i}"}]} for i in range(11)]
		resp = self.mock_api.dispatch_request(
			method="POST",
			url="https://graph.facebook.com/v18.0/100200300/messages",
			headers={"Authorization": "Bearer VALID_TOKEN"},
			json_data={
				"messaging_product": "whatsapp",
				"to": "15551234567",
				"type": "interactive",
				"interactive": {
					"type": "product_list",
					"action": {"catalog_id": "CATALOG_1", "sections": sections},
				},
			},
		)
		self.assertEqual(resp.status_code, 400)
		self.assertIn("10 sections", resp.json()["error"]["message"])

	def test_payload_validation_media_missing_id_and_link(self):
		"""Media message missing both id and link returns HTTP 400."""
		resp = self.mock_api.dispatch_request(
			method="POST",
			url="https://graph.facebook.com/v18.0/100200300/messages",
			headers={"Authorization": "Bearer VALID_TOKEN"},
			json_data={
				"messaging_product": "whatsapp",
				"to": "15551234567",
				"type": "image",
				"image": {"caption": "No media specified"},
			},
		)
		self.assertEqual(resp.status_code, 400)
		self.assertIn("either 'id' or 'link'", resp.json()["error"]["message"])

	def test_mark_as_read_payload_success(self):
		"""Valid mark_as_read payload returns {"success": true}."""
		resp = self.mock_api.dispatch_request(
			method="POST",
			url="https://graph.facebook.com/v18.0/100200300/messages",
			headers={"Authorization": "Bearer VALID_TOKEN"},
			json_data={"messaging_product": "whatsapp", "status": "read", "message_id": "wamid.TEST12345"},
		)
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.json(), {"success": True})


class TestOutboundDirectMetaConnectorMocked(unittest.TestCase):
	"""2. Outbound testing via DirectMetaCloudApiConnector backed by MockWhatsAppCloudApi."""

	def setUp(self):
		super().setUp()
		self.channel_cfg = {
			"channel_name": "Direct Meta Channel",
			"phone_number_id": "100200300",
			"access_token": "EAABtesttoken1234567890",
			"api_version": "v18.0",
			"api_base_url": "https://graph.facebook.com",
			"status": "Active",
		}
		self.connector = DirectMetaCloudApiConnector()

	def test_send_text_success(self):
		"""DirectMetaCloudApiConnector sends text successfully via MockWhatsAppCloudApi."""
		with MockWhatsAppCloudApi() as mock_api:
			res = self.connector.send_text(
				self.channel_cfg,
				to="+1 (555) 234-5678",
				text="Hello from hermetic mock test!",
			)
			self.assertTrue(res["success"])
			self.assertEqual(res["to"], "15552345678")
			self.assertTrue(res["message_id"].startswith("wamid."))

			sent = mock_api.get_last_message()
			self.assertIsNotNone(sent)
			self.assertEqual(sent["to"], "15552345678")
			self.assertEqual(sent["payload"]["text"]["body"], "Hello from hermetic mock test!")

	def test_send_template_success(self):
		"""DirectMetaCloudApiConnector sends template with parameters."""
		components = [
			{
				"type": "body",
				"parameters": [
					{"type": "text", "text": "Alice"},
					{"type": "text", "text": "$49.99"},
				],
			}
		]
		with MockWhatsAppCloudApi() as mock_api:
			res = self.connector.send_template(
				self.channel_cfg,
				to="+15552345678",
				template_name="order_confirmation",
				language_code="en_US",
				components=components,
			)
			self.assertTrue(res["success"])
			self.assertTrue(res["message_id"].startswith("wamid."))

			sent = mock_api.get_last_message()
			self.assertEqual(sent["type"], "template")
			self.assertEqual(sent["payload"]["template"]["name"], "order_confirmation")
			self.assertEqual(sent["payload"]["template"]["language"]["code"], "en_US")
			self.assertEqual(sent["payload"]["template"]["components"], components)

	def test_send_media_image_url(self):
		"""DirectMetaCloudApiConnector sends image media by URL link."""
		with MockWhatsAppCloudApi() as mock_api:
			res = self.connector.send_media(
				self.channel_cfg,
				to="+15552345678",
				media_id_or_url="https://example.com/assets/banner.png",
				mime_type="image/png",
				caption="Spring Promo Sale",
			)
			self.assertTrue(res["success"])
			sent = mock_api.get_last_message()
			self.assertEqual(sent["type"], "image")
			self.assertEqual(sent["payload"]["image"]["link"], "https://example.com/assets/banner.png")
			self.assertEqual(sent["payload"]["image"]["caption"], "Spring Promo Sale")

	def test_send_media_document_id(self):
		"""DirectMetaCloudApiConnector sends document by Meta media ID."""
		with MockWhatsAppCloudApi() as mock_api:
			res = self.connector.send_media(
				self.channel_cfg,
				to="+15552345678",
				media_id_or_url="998877665544332211",
				mime_type="application/pdf",
				caption="Your Invoice",
				filename="Invoice-2026.pdf",
			)
			self.assertTrue(res["success"])
			sent = mock_api.get_last_message()
			self.assertEqual(sent["type"], "document")
			self.assertEqual(sent["payload"]["document"]["id"], "998877665544332211")
			self.assertEqual(sent["payload"]["document"]["filename"], "Invoice-2026.pdf")

	def test_send_media_sticker(self):
		"""DirectMetaCloudApiConnector sends sticker media."""
		with MockWhatsAppCloudApi() as mock_api:
			res = self.connector.send_media(
				self.channel_cfg,
				to="+15552345678",
				media_id_or_url="8877665544",
				mime_type="image/webp",
				is_sticker=True,
			)
			self.assertTrue(res["success"])
			sent = mock_api.get_last_message()
			self.assertEqual(sent["type"], "sticker")
			self.assertEqual(sent["payload"]["sticker"]["id"], "8877665544")

	def test_send_interactive_spm(self):
		"""DirectMetaCloudApiConnector sends Single-Product Message (SPM)."""
		spm_payload = build_spm_payload(
			catalog_id="CAT_9876",
			product_retailer_id="SKU_RED_SHOE",
			body_text="Check out this premium running shoe",
			footer_text="Free returns within 30 days",
		)
		with MockWhatsAppCloudApi() as mock_api:
			res = self.connector.send_interactive(
				self.channel_cfg,
				to="+15552345678",
				interactive_payload=spm_payload,
			)
			self.assertTrue(res["success"])
			sent = mock_api.get_last_message()
			self.assertEqual(sent["type"], "interactive")
			self.assertEqual(sent["payload"]["interactive"]["type"], "product")
			self.assertEqual(sent["payload"]["interactive"]["action"]["catalog_id"], "CAT_9876")
			self.assertEqual(sent["payload"]["interactive"]["action"]["product_retailer_id"], "SKU_RED_SHOE")

	def test_send_interactive_mpm(self):
		"""DirectMetaCloudApiConnector sends Multi-Product Message (MPM)."""
		sections = [
			{
				"title": "Footwear",
				"product_items": [{"product_retailer_id": "SKU_BOOT"}, {"product_retailer_id": "SKU_SNEAKER"}],
			},
			{
				"title": "Apparel",
				"product_items": [{"product_retailer_id": "SKU_HOODIE"}],
			},
		]
		mpm_payload = build_mpm_payload(
			catalog_id="CAT_9876",
			sections=sections,
			body_text="Explore our featured collection",
			header_text="Autumn Collection",
			footer_text="Limited time offer",
		)
		with MockWhatsAppCloudApi() as mock_api:
			res = self.connector.send_interactive(
				self.channel_cfg,
				to="+15552345678",
				interactive_payload=mpm_payload,
			)
			self.assertTrue(res["success"])
			sent = mock_api.get_last_message()
			self.assertEqual(sent["type"], "interactive")
			self.assertEqual(sent["payload"]["interactive"]["type"], "product_list")
			self.assertEqual(len(sent["payload"]["interactive"]["action"]["sections"]), 2)

	def test_mark_as_read(self):
		"""DirectMetaCloudApiConnector marks incoming message as read."""
		with MockWhatsAppCloudApi() as mock_api:
			ok = self.connector.mark_as_read(
				self.channel_cfg,
				message_id="wamid.HBgLMTU1NTEyMzQ1NjcVAgASGBQ=",
			)
			self.assertTrue(ok)
			last_req = mock_api.requests_history[-1]
			self.assertEqual(last_req["json"]["status"], "read")
			self.assertEqual(last_req["json"]["message_id"], "wamid.HBgLMTU1NTEyMzQ1NjcVAgASGBQ=")

	def test_retry_and_exponential_backoff_on_429(self):
		"""Connector retries on simulated 429 rate limit and succeeds on subsequent try."""
		with MockWhatsAppCloudApi() as mock_api:
			# Fail 2 times with 429, then succeed on 3rd request
			mock_api.set_rate_limit(retry_after=0.01, fail_count=2)

			res = self.connector.send_text(
				self.channel_cfg,
				to="+15551234567",
				text="Testing 429 exponential backoff",
			)
			self.assertTrue(res["success"])
			# Assert that exactly 3 requests were made (2 retries + 1 success)
			self.assertEqual(len(mock_api.requests_history), 3)

	def test_retry_and_exponential_backoff_on_503(self):
		"""Connector retries on simulated 503 service unavailable and succeeds on subsequent try."""
		with MockWhatsAppCloudApi() as mock_api:
			# Fail 2 times with 503, then succeed on 3rd request
			mock_api.set_service_unavailable(retry_after=0.01, fail_count=2)

			res = self.connector.send_text(
				self.channel_cfg,
				to="+15551234567",
				text="Testing 503 service unavailable retry",
			)
			self.assertTrue(res["success"])
			self.assertEqual(len(mock_api.requests_history), 3)

	def test_rate_limit_retry_exhaustion(self):
		"""Connector raises WhatsAppRateLimitError when retries exceed max_rate_limit_retries."""
		with MockWhatsAppCloudApi() as mock_api:
			# Fail 5 times (> max default 3 retries)
			mock_api.set_rate_limit(retry_after=0.01, fail_count=5)

			with self.assertRaises(WhatsAppRateLimitError) as ctx:
				self.connector.send_text(
					self.channel_cfg,
					to="+15551234567",
					text="Should exhaust retries",
				)
			self.assertIn("rate limit exceeded", str(ctx.exception).lower())

	def test_token_scrubbing_on_simulated_401(self):
		"""Connector sanitizes secret tokens from exceptions on 401 authentication errors."""
		secret_token = "EAABSECRET_META_KEY_998877"
		cfg = dict(self.channel_cfg)
		cfg["access_token"] = secret_token

		with MockWhatsAppCloudApi() as mock_api:
			mock_api.set_oauth_error(
				status_code=401,
				code=190,
				message=f"Error validating access token: {secret_token} has expired.",
			)

			with self.assertRaises(WhatsAppAuthError) as ctx:
				self.connector.send_text(cfg, to="+15551234567", text="Auth error test")

			err_str = str(ctx.exception)
			# The raw token must NOT be present in exception string
			self.assertNotIn(secret_token, err_str)
			# Sanitized placeholder must be present
			self.assertIn("EAAB[REDACTED]", err_str)


class TestInboundWebhookMocked(unittest.TestCase):
	"""3. Inbound webhook testing using payloads generated by MockWhatsAppCloudApi."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "request", "form_dict", "response", "lang"):
			self._saved[name] = getattr(frappe.local, name, None) if hasattr(frappe, "local") else None
		self._saved_cache = getattr(frappe, "cache", None)

		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Guest", data=frappe._dict())
		frappe.local.lang = "en"
		self.mock_db = MagicMock()
		frappe.local.db = self.mock_db
		frappe.local.response = frappe._dict()
		frappe.local.form_dict = frappe._dict()

		frappe.cache = MagicMock()
		frappe.cache.hget.return_value = {}

		self.mock_request = MagicMock()
		self.mock_request.method = "POST"
		frappe.local.request = self.mock_request

		self.app_secret = "test_meta_webhook_secret_key_123"

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

	def _setup_webhook_request(self, payload: dict, signature: str | None = None, use_valid_sig: bool = True):
		raw_bytes = json.dumps(payload).encode("utf-8")
		if signature is None and use_valid_sig:
			signature = MockWhatsAppCloudApi.compute_hub_signature(raw_bytes, self.app_secret)
		self.mock_request.get_data.return_value = raw_bytes
		return raw_bytes, signature

	def test_webhook_hmac_signature_validation_success(self):
		"""POST with valid HMAC-SHA256 signature passes verification."""
		payload = MockWhatsAppCloudApi.generate_text_webhook("100200300", "15551234567", "Hello")
		raw_bytes, signature = self._setup_webhook_request(payload)

		with patch("frappe.get_request_header", return_value=signature):
			with patch.object(webhook, "_resolve_channel", return_value=None):
				with patch.object(webhook, "_get_webhook_secret", return_value=self.app_secret):
					with patch.object(webhook, "_process_messages_field") as mock_proc:
						resp = webhook.handler()
						self.assertEqual(resp, "ok")
						mock_proc.assert_called_once()

	def test_webhook_hmac_signature_mismatch_fails(self):
		"""POST with invalid HMAC signature raises frappe.AuthenticationError."""
		payload = MockWhatsAppCloudApi.generate_text_webhook("100200300", "15551234567", "Hello")
		raw_bytes, _ = self._setup_webhook_request(payload)

		with patch("frappe.get_request_header", return_value="sha256=invalidhash998877"):
			with patch.object(webhook, "_resolve_channel", return_value=None):
				with patch.object(webhook, "_get_webhook_secret", return_value=self.app_secret):
					with self.assertRaises(frappe.AuthenticationError):
						webhook.handler()

	def test_inbound_text_message_and_contact_creation(self):
		"""Inbound text webhook resolves/creates contact and saves incoming message."""
		payload = MockWhatsAppCloudApi.generate_text_webhook(
			phone_number_id="100200300",
			from_wa_id="15559876543",
			text="I need support with my order",
			profile_name="Bob Builder",
		)
		raw_bytes, signature = self._setup_webhook_request(payload)

		with patch("frappe.get_request_header", return_value=signature):
			with patch.object(webhook, "_resolve_channel", return_value=None):
				with patch.object(webhook, "_get_webhook_secret", return_value=self.app_secret):
					with patch.object(DeskMessageRepository, "is_duplicate_message", return_value=False):
						with patch.object(DeskContactRepository, "get_or_create_contact", return_value="CONTACT-BOB") as mock_contact:
							with patch.object(DeskMessageRepository, "save_incoming_message", return_value={"record_name": "MSG-001", "content": "I need support with my order"}) as mock_save:
								with patch.object(consent, "handle_incoming_consent", return_value=(False, None)):
									with patch.object(webhook, "_trigger_automations"):
										resp = webhook.handler()
										self.assertEqual(resp, "ok")
										mock_contact.assert_called_once_with(
											wa_id="15559876543",
											profile_name="Bob Builder",
											account_or_channel="",
										)
										mock_save.assert_called_once()

	def test_inbound_order_cart_parsing(self):
		"""Inbound order cart webhook parses cart items and formats markdown transcript."""
		items = [
			{"product_retailer_id": "SKU-PRO-MAX", "quantity": 2, "item_price": 99.00, "currency": "USD"},
			{"product_retailer_id": "SKU-CASE", "quantity": 1, "item_price": 25.00, "currency": "USD"},
		]
		payload = MockWhatsAppCloudApi.generate_order_cart_webhook(
			phone_number_id="100200300",
			from_wa_id="15559876543",
			catalog_id="CAT_8899",
			product_items=items,
			customer_text="Please gift wrap",
		)
		msg_dict = payload["entry"][0]["changes"][0]["value"]["messages"][0]

		# Verify parse_inbound_order logic directly
		parsed = catalog.parse_inbound_order(msg_dict["order"])
		self.assertEqual(parsed["catalog_id"], "CAT_8899")
		self.assertEqual(parsed["total_price"], 223.00)
		self.assertEqual(parsed["item_count"], 2)
		self.assertIn("SKU-PRO-MAX", parsed["summary_text"])
		self.assertIn("Please gift wrap", parsed["summary_text"])

		# Verify through message repository save_incoming_message
		with patch.object(DeskMessageRepository, "is_self_hosted", return_value=True):
			self.mock_db.exists.side_effect = lambda dt, name=None: dt in ("DocType", "WA Message")
			mock_doc = MagicMock()
			mock_doc.name = "MSG-ORDER-001"
			with patch("frappe.get_doc", return_value=mock_doc):
				saved = DeskMessageRepository.save_incoming_message(
					channel_name="Direct Channel",
					msg=msg_dict,
					contact_id="CONTACT-ALICE",
					contact_name="Alice",
				)
				self.assertIn("🛒 Order Placed", saved["content"])
				self.assertIn("SKU-PRO-MAX", saved["content"])

	def test_stop_keyword_consent_interception(self):
		"""Inbound STOP keyword updates consent to Opted-Out and suppresses away message."""
		payload = MockWhatsAppCloudApi.generate_text_webhook(
			phone_number_id="100200300",
			from_wa_id="15559876543",
			text="STOP",
		)
		raw_bytes, signature = self._setup_webhook_request(payload)

		with patch("frappe.get_request_header", return_value=signature):
			with patch.object(webhook, "_resolve_channel", return_value=None):
				with patch.object(webhook, "_get_webhook_secret", return_value=self.app_secret):
					with patch.object(DeskMessageRepository, "is_duplicate_message", return_value=False):
						with patch.object(DeskContactRepository, "get_or_create_contact", return_value="CONTACT-USER"):
							with patch.object(DeskMessageRepository, "save_incoming_message", return_value={"record_name": "MSG-STOP", "content": "STOP"}):
								with patch.object(DeskContactRepository, "update_consent") as mock_update_consent:
									resp = webhook.handler()
									self.assertEqual(resp, "ok")
									mock_update_consent.assert_called_once_with(
										"CONTACT-USER", "Opted-Out", reason="STOP keyword"
									)

	def test_status_update_delivery_progression(self):
		"""Message status progresses Sent -> Delivered -> Read with precedence protection."""
		with patch.object(DeskMessageRepository, "is_self_hosted", return_value=True):
			self.mock_db.exists.side_effect = lambda dt, filters=None: dt in ("DocType", "WA Message")
			self.mock_db.get_value.side_effect = lambda dt, filters, fieldname=None: (
				"DOC-MSG-1" if isinstance(filters, dict) and filters.get("message_id") == "wamid.TEST1"
				else "Sent" if fieldname == "status" and filters == "DOC-MSG-1"
				else None
			)

			ok = DeskMessageRepository.update_message_status(
				message_id="wamid.TEST1",
				new_status_raw="delivered",
				timestamp="1700000000",
			)
			self.assertTrue(ok)
			self.mock_db.set_value.assert_called_with("WA Message", "DOC-MSG-1", {"status": "Delivered"})

			self.mock_db.get_value.side_effect = lambda dt, filters, fieldname=None: (
				"DOC-MSG-1" if isinstance(filters, dict) and filters.get("message_id") == "wamid.TEST1"
				else "Delivered" if fieldname == "status" and filters == "DOC-MSG-1"
				else None
			)
			ok2 = DeskMessageRepository.update_message_status(
				message_id="wamid.TEST1",
				new_status_raw="read",
				timestamp="1700000010",
			)
			self.assertTrue(ok2)
			self.mock_db.set_value.assert_called_with("WA Message", "DOC-MSG-1", {"status": "Read"})

			# 3. Guard: Attempt to regress from Read back to Delivered must fail
			self.mock_db.get_value.side_effect = lambda dt, filters, fieldname=None: (
				"DOC-MSG-1" if isinstance(filters, dict) and filters.get("message_id") == "wamid.TEST1"
				else "Read" if fieldname == "status" and filters == "DOC-MSG-1"
				else None
			)
			self.mock_db.set_value.reset_mock()
			ok3 = DeskMessageRepository.update_message_status(
				message_id="wamid.TEST1",
				new_status_raw="delivered",
				timestamp="1700000020",
			)
			self.assertFalse(ok3)
			self.mock_db.set_value.assert_not_called()


class TestCampaignEndToEndMocked(unittest.TestCase):
	"""3. Campaign broadcast and funnel tracking end-to-end flow with MockWhatsAppCloudApi."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "request", "form_dict", "response", "lang"):
			self._saved[name] = getattr(frappe.local, name, None) if hasattr(frappe, "local") else None
		self._saved_cache = getattr(frappe, "cache", None)

		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Administrator")
		self.mock_db = MagicMock()
		frappe.local.db = self.mock_db
		frappe.local.response = frappe._dict()

		frappe.cache = MagicMock()
		frappe.cache.hget.return_value = {}

		self.channel_doc = {
			"name": "Direct Meta Channel",
			"channel_name": "Direct Meta Channel",
			"connector_type": "Meta Cloud API Direct",
			"phone_number_id": "100200300",
			"access_token": "EAABvalidtoken12345",
			"api_version": "v18.0",
			"api_base_url": "https://graph.facebook.com",
			"status": "Active",
		}

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

	def test_campaign_end_to_end_broadcast_and_funnel(self):
		"""Run campaign through DirectMetaCloudApiConnector and verify funnel analytics progression."""
		# Setup Campaign Document with 2 Pending recipients
		recipients = [
			frappe._dict({
				"name": "rec-1",
				"phone_number": "+15551112222",
				"profile": "Alice",
				"status": "Pending",
				"variables_json": '["Alice", "10%"]',
				"message": None,
				"message_id": None,
				"error_message": None,
			}),
			frappe._dict({
				"name": "rec-2",
				"phone_number": "+15553334444",
				"profile": "Bob",
				"status": "Pending",
				"variables_json": '["Bob", "20%"]',
				"message": None,
				"message_id": None,
				"error_message": None,
			}),
		]

		campaign_doc = frappe._dict({
			"name": "CAMP-SUMMER-01",
			"campaign_name": "Summer Discount Promo",
			"whatsapp_channel": self.channel_doc,
			"whatsapp_account": None,
			"whatsapp_template": "summer_promo",
			"template": "summer_promo",
			"whatsapp_status": "Draft",
			"status": "Draft",
			"whatsapp_sent_count": 0,
			"sent_count": 0,
			"whatsapp_delivered_count": 0,
			"delivered_count": 0,
			"whatsapp_read_count": 0,
			"read_count": 0,
			"whatsapp_failed_count": 0,
			"failed_count": 0,
			"whatsapp_last_error": None,
			"last_error": None,
			"whatsapp_recipients": recipients,
			"recipients": recipients,
			"save": MagicMock(),
		})

		def mock_sql_query(query, params=None, as_dict=False):
			q = str(query).lower()
			if "from `tabwhatsapp campaign recipient`" in q and "where message_id = %s or message = %s" in q:
				lookup_id = params[0] if params else None
				for r in campaign_doc.recipients:
					if getattr(r, "message_id", None) == lookup_id or getattr(r, "message", None) == lookup_id:
						return [{"name": r.name, "parent": campaign_doc.name, "status": r.status}]
				return []

			if "sum(case when status in ('sent', 'delivered', 'read')" in q:
				sent = sum(1 for r in campaign_doc.recipients if r.status in ("Sent", "Delivered", "Read"))
				deliv = sum(1 for r in campaign_doc.recipients if r.status in ("Delivered", "Read"))
				read = sum(1 for r in campaign_doc.recipients if r.status == "Read")
				fail = sum(1 for r in campaign_doc.recipients if r.status == "Failed")
				return [{
					"sent_count": sent,
					"delivered_count": deliv,
					"read_count": read,
					"failed_count": fail,
				}]
			return []

		self.mock_db.sql.side_effect = mock_sql_query

		def mock_set_value(dt, docname, field_dict, update_modified=True):
			if dt == "WhatsApp Campaign Recipient":
				for r in campaign_doc.recipients:
					if r.name == docname:
						if isinstance(field_dict, dict):
							for k, v in field_dict.items():
								setattr(r, k, v)
			elif dt in ("WhatsApp Campaign", "UTM Campaign"):
				if isinstance(field_dict, dict):
					for k, v in field_dict.items():
						setattr(campaign_doc, k, v)

		self.mock_db.set_value.side_effect = mock_set_value
		self.mock_db.exists.side_effect = lambda dt, name=None: True if dt in ("DocType", "WhatsApp Campaign Recipient", "UTM Campaign", "WhatsApp Campaign") else False
		self.mock_db.has_column.return_value = True

		# Step 1: Execute Campaign Run within MockWhatsAppCloudApi
		with MockWhatsAppCloudApi() as mock_api:
			with patch("frappe.get_doc", return_value=campaign_doc):
				with patch("frappe.has_permission", return_value=True):
					with patch.object(campaigns, "check_recipient_consent", return_value=True):
						run_res = campaigns.run_campaign("CAMP-SUMMER-01")

			# Verify outbound requests were handled by mock API
			self.assertEqual(len(mock_api.sent_messages), 2)
			self.assertEqual(run_res["status"], "Completed")
			self.assertEqual(run_res["sent_count"], 2)

			# Record generated wamids in our simulated database
			msg_id_1 = campaign_doc.recipients[0].message_id
			msg_id_2 = campaign_doc.recipients[1].message_id
			self.assertTrue(msg_id_1.startswith("wamid."))
			self.assertTrue(msg_id_2.startswith("wamid."))

			# Initial Funnel assertion: 2 Sent, 0 Delivered, 0 Read
			funnel = campaigns.recalculate_campaign_funnel_counts("CAMP-SUMMER-01")
			self.assertEqual(funnel["sent_count"], 2)
			self.assertEqual(funnel["delivered_count"], 0)
			self.assertEqual(funnel["read_count"], 0)

			# Step 2: Inbound Webhook delivers status update: recipient 1 Delivered
			status_wh_1 = MockWhatsAppCloudApi.generate_status_update_webhook(
				phone_number_id="100200300",
				recipient_wa_id="15551112222",
				message_id=msg_id_1,
				status="delivered",
			)
			status_dict_1 = status_wh_1["entry"][0]["changes"][0]["value"]["statuses"][0]
			webhook._process_status_update(status_dict_1, channel_doc=self.channel_doc)

			# Funnel assertion: 2 Sent, 1 Delivered, 0 Read
			funnel = campaigns.recalculate_campaign_funnel_counts("CAMP-SUMMER-01")
			self.assertEqual(funnel["sent_count"], 2)
			self.assertEqual(funnel["delivered_count"], 1)
			self.assertEqual(funnel["read_count"], 0)

			# Step 3: Inbound Webhook delivers status update: recipient 1 Read
			status_wh_1_read = MockWhatsAppCloudApi.generate_status_update_webhook(
				phone_number_id="100200300",
				recipient_wa_id="15551112222",
				message_id=msg_id_1,
				status="read",
			)
			status_dict_1_read = status_wh_1_read["entry"][0]["changes"][0]["value"]["statuses"][0]
			webhook._process_status_update(status_dict_1_read, channel_doc=self.channel_doc)

			# Funnel assertion: 2 Sent, 1 Delivered, 1 Read
			funnel = campaigns.recalculate_campaign_funnel_counts("CAMP-SUMMER-01")
			self.assertEqual(funnel["sent_count"], 2)
			self.assertEqual(funnel["delivered_count"], 1)
			self.assertEqual(funnel["read_count"], 1)

			# Step 4: Inbound Webhook delivers status update: recipient 2 Delivered & Read
			status_wh_2 = MockWhatsAppCloudApi.generate_status_update_webhook(
				phone_number_id="100200300",
				recipient_wa_id="15553334444",
				message_id=msg_id_2,
				status="delivered",
			)
			status_dict_2 = status_wh_2["entry"][0]["changes"][0]["value"]["statuses"][0]
			webhook._process_status_update(status_dict_2, channel_doc=self.channel_doc)

			status_wh_2_read = MockWhatsAppCloudApi.generate_status_update_webhook(
				phone_number_id="100200300",
				recipient_wa_id="15553334444",
				message_id=msg_id_2,
				status="read",
			)
			status_dict_2_read = status_wh_2_read["entry"][0]["changes"][0]["value"]["statuses"][0]
			webhook._process_status_update(status_dict_2_read, channel_doc=self.channel_doc)

			# Final Funnel assertion: 2 Sent, 2 Delivered, 2 Read, 0 Failed
			funnel = campaigns.recalculate_campaign_funnel_counts("CAMP-SUMMER-01")
			self.assertEqual(funnel["sent_count"], 2)
			self.assertEqual(funnel["delivered_count"], 2)
			self.assertEqual(funnel["read_count"], 2)
			self.assertEqual(funnel["failed_count"], 0)


if __name__ == "__main__":
	unittest.main()
