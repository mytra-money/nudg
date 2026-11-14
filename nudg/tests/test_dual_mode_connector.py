# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import frappe
import requests

from nudg.integrations.connector.base import (
	AuthenticationError,
	BaseWhatsAppConnector,
	ConnectorError,
	RateLimitError,
	WhatsAppAuthError,
	WhatsAppConnectorError,
	WhatsAppPayloadError,
	WhatsAppRateLimitError,
)
from nudg.integrations.connector.factory import (
	clear_connector_cache,
	get_connector,
)
from nudg.integrations.connector.meta_cloud import DirectMetaCloudApiConnector
from nudg.integrations.connector.saas_gateway import SaaSGatewayConnector
from nudg.integrations.connector.self_hosted import SelfHostedFrappeConnector


class TestDualModeConnector(unittest.TestCase):
	"""Unit tests verifying connector contracts, retries, and isolation."""

	def setUp(self):
		super().setUp()
		clear_connector_cache()
		self._saved_cache = getattr(frappe, "cache", None)
		self.mock_cache = MagicMock()
		self.mock_cache.get_value.return_value = 0
		self.mock_cache.hget.return_value = {}
		frappe.cache = MagicMock(return_value=self.mock_cache)
		frappe.cache.hget.return_value = {}

	def tearDown(self):
		clear_connector_cache()
		frappe.cache = self._saved_cache
		super().tearDown()

	def test_base_connector_is_abstract(self):
		"""BaseWhatsAppConnector cannot be instantiated directly."""
		with self.assertRaises(TypeError):
			BaseWhatsAppConnector()  # type: ignore

	def test_exception_aliases(self):
		"""Ensure exception backward-compatible aliases exist."""
		self.assertTrue(issubclass(AuthenticationError, WhatsAppConnectorError))
		self.assertTrue(issubclass(RateLimitError, WhatsAppConnectorError))
		self.assertTrue(issubclass(ConnectorError, Exception))

	def test_factory_resolution_self_hosted(self):
		"""Factory returns SelfHostedFrappeConnector for self-hosted channel."""
		channel = {
			"channel_name": "Local Support",
			"connector_type": "Self-Hosted (frappe_whatsapp)",
		}
		connector = get_connector(channel)
		self.assertIsInstance(connector, SelfHostedFrappeConnector)

	def test_factory_resolution_meta_direct(self):
		"""Factory returns DirectMetaCloudApiConnector for direct Meta channel."""
		channel = {
			"channel_name": "Direct Support",
			"connector_type": "Meta Cloud API Direct",
		}
		connector = get_connector(channel)
		self.assertIsInstance(connector, DirectMetaCloudApiConnector)

	def test_meta_cloud_send_text_payload_contract(self):
		"""DirectMetaCloudApiConnector sends valid v18.0 text message payload."""
		connector = DirectMetaCloudApiConnector()
		channel_cfg = {
			"phone_number_id": "100200300",
			"access_token": "TEST_TOKEN_123",
			"api_version": "v18.0",
			"api_base_url": "https://graph.facebook.com",
		}

		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {
			"messaging_product": "whatsapp",
			"contacts": [{"input": "15551234567", "wa_id": "15551234567"}],
			"messages": [{"id": "wamid.HBgLMTU1NTEyMzQ1NjcVAgASGBQ="}],
		}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			result = connector.send_text(channel_cfg, to="+1 (555) 123-4567", text="Hello world")

			self.assertTrue(result["success"])
			self.assertEqual(result["message_id"], "wamid.HBgLMTU1NTEyMzQ1NjcVAgASGBQ=")
			self.assertEqual(result["to"], "15551234567")

			mock_req.assert_called_once()
			call_kwargs = mock_req.call_args[1]
			self.assertEqual(call_kwargs["method"], "POST")
			self.assertEqual(
				call_kwargs["url"],
				"https://graph.facebook.com/v18.0/100200300/messages",
			)
			self.assertIn("Authorization", call_kwargs["headers"])
			self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer TEST_TOKEN_123")
			expected_payload = {
				"messaging_product": "whatsapp",
				"recipient_type": "individual",
				"to": "15551234567",
				"type": "text",
				"text": {"preview_url": False, "body": "Hello world"},
			}
			self.assertEqual(call_kwargs["json"], expected_payload)

	def test_meta_cloud_send_media_payload_contract(self):
		"""DirectMetaCloudApiConnector formats media payloads correctly."""
		connector = DirectMetaCloudApiConnector()
		channel_cfg = {
			"phone_number_id": "100200300",
			"access_token": "TEST_TOKEN_123",
		}

		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.MEDIA123"}]}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			result = connector.send_media(
				channel_cfg,
				to="15559876543",
				media_id_or_url="https://example.com/banner.jpg",
				mime_type="image/jpeg",
				caption="Spring Promo",
			)
			self.assertEqual(result["message_id"], "wamid.MEDIA123")
			call_json = mock_req.call_args[1]["json"]
			self.assertEqual(call_json["type"], "image")
			self.assertEqual(call_json["image"]["link"], "https://example.com/banner.jpg")
			self.assertEqual(call_json["image"]["caption"], "Spring Promo")

	def test_meta_cloud_send_template_payload_contract(self):
		"""DirectMetaCloudApiConnector formats template messages with components."""
		connector = DirectMetaCloudApiConnector()
		channel_cfg = {
			"phone_number_id": "100200300",
			"access_token": "TEST_TOKEN_123",
		}

		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.TMPL123"}]}

		components = [
			{
				"type": "body",
				"parameters": [{"type": "text", "text": "Alice"}, {"type": "text", "text": "$99"}],
			}
		]

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			result = connector.send_template(
				channel_cfg,
				to="15559876543",
				template_name="order_confirmation",
				language_code="en_US",
				components=components,
			)
			self.assertEqual(result["message_id"], "wamid.TMPL123")
			call_json = mock_req.call_args[1]["json"]
			self.assertEqual(call_json["type"], "template")
			self.assertEqual(call_json["template"]["name"], "order_confirmation")
			self.assertEqual(call_json["template"]["language"]["code"], "en_US")
			self.assertEqual(call_json["template"]["components"], components)

	def test_meta_cloud_send_interactive_payload_contract(self):
		"""DirectMetaCloudApiConnector formats interactive messages."""
		connector = DirectMetaCloudApiConnector()
		channel_cfg = {
			"phone_number_id": "100200300",
			"access_token": "TEST_TOKEN_123",
		}

		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.INT123"}]}

		interactive_data = {
			"type": "button",
			"body": {"text": "Select an option"},
			"action": {
				"buttons": [
					{"type": "reply", "reply": {"id": "opt_1", "title": "Support"}},
					{"type": "reply", "reply": {"id": "opt_2", "title": "Sales"}},
				]
			},
		}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			result = connector.send_interactive(
				channel_cfg,
				to="15559876543",
				interactive_payload=interactive_data,
			)
			self.assertEqual(result["message_id"], "wamid.INT123")
			call_json = mock_req.call_args[1]["json"]
			self.assertEqual(call_json["type"], "interactive")
			self.assertEqual(call_json["interactive"], interactive_data)

	def test_meta_cloud_mark_as_read_payload_contract(self):
		"""DirectMetaCloudApiConnector formats mark_as_read payloads."""
		connector = DirectMetaCloudApiConnector()
		channel_cfg = {
			"phone_number_id": "100200300",
			"access_token": "TEST_TOKEN_123",
		}

		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"success": True}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			ok = connector.mark_as_read(channel_cfg, "wamid.INBOUND123")
			self.assertTrue(ok)
			call_json = mock_req.call_args[1]["json"]
			self.assertEqual(call_json["status"], "read")
			self.assertEqual(call_json["message_id"], "wamid.INBOUND123")

	def test_meta_cloud_exponential_backoff_on_429(self):
		"""Connector retries on HTTP 429 and succeeds on subsequent try."""
		connector = DirectMetaCloudApiConnector()
		channel_cfg = {
			"phone_number_id": "100200300",
			"access_token": "TEST_TOKEN_123",
		}

		resp_429 = MagicMock(spec=requests.Response)
		resp_429.status_code = 429
		resp_429.headers = {"Retry-After": "0.01"}
		resp_429.json.return_value = {"error": {"message": "Rate limit exceeded", "code": 80007}}

		resp_200 = MagicMock(spec=requests.Response)
		resp_200.status_code = 200
		resp_200.json.return_value = {"messages": [{"id": "wamid.RETRY_OK"}]}

		with patch.object(connector.session, "request", side_effect=[resp_429, resp_200]) as mock_req:
			with patch("time.sleep") as mock_sleep:
				result = connector.send_text(channel_cfg, to="15551234567", text="Retry test")
				self.assertEqual(result["message_id"], "wamid.RETRY_OK")
				self.assertEqual(mock_req.call_count, 2)
				mock_sleep.assert_called_once()

	def test_meta_cloud_zero_secret_leak_in_exceptions(self):
		"""Connector redacts access token from error messages."""
		connector = DirectMetaCloudApiConnector()
		channel_cfg = {
			"phone_number_id": "100200300",
			"access_token": "EAABsecretkey123456789",
		}

		resp_err = MagicMock(spec=requests.Response)
		resp_err.status_code = 400
		resp_err.text = "Invalid request with token EAABsecretkey123456789"
		resp_err.json.return_value = {
			"error": {
				"message": "Invalid request for token EAABsecretkey123456789",
				"code": 100,
			}
		}

		with patch.object(connector.session, "request", return_value=resp_err):
			with self.assertRaises(WhatsAppConnectorError) as ctx:
				connector.send_text(channel_cfg, to="15551234567", text="Secret test")
			err_str = str(ctx.exception)
			self.assertNotIn("EAABsecretkey123456789", err_str)
			self.assertIn("EAAB[REDACTED]", err_str)

	def test_factory_resolution_saas_gateway(self):
		"""Factory returns SaaSGatewayConnector for SaaS Gateway channel."""
		channel = {
			"channel_name": "SaaS Cloud Hub",
			"connector_type": "SaaS Gateway / Webhook",
		}
		connector = get_connector(channel)
		self.assertIsInstance(connector, SaaSGatewayConnector)

	def test_saas_gateway_send_text_payload_and_headers(self):
		"""SaaSGatewayConnector dispatches text messages with tenant headers."""
		connector = SaaSGatewayConnector()
		channel_cfg = {
			"channel_name": "Cloud Hub 1",
			"gateway_url": "https://gateway.mytra.money",
			"api_key": "sk-test-secret-api-key-12345",
		}

		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {
			"success": True,
			"message_id": "saas_msg_998877",
			"status": "sent",
		}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			res = connector.send_text(channel_cfg, to="+919830122891", text="Hello from SaaS")
			self.assertTrue(res["success"])
			self.assertEqual(res["message_id"], "saas_msg_998877")

			call_args = mock_req.call_args
			self.assertEqual(call_args.kwargs["method"], "POST")
			self.assertEqual(call_args.kwargs["url"], "https://gateway.mytra.money/api/v1/whatsapp/messages")
			headers = call_args.kwargs["headers"]
			self.assertEqual(headers["Authorization"], "Bearer sk-test-secret-api-key-12345")
			self.assertEqual(headers["X-Channel-Name"], "Cloud Hub 1")
			payload = call_args.kwargs["json"]
			self.assertEqual(payload["to"], "+919830122891")
			self.assertEqual(payload["text"]["body"], "Hello from SaaS")

	def test_saas_gateway_send_template(self):
		"""SaaSGatewayConnector sends approved template payload."""
		connector = SaaSGatewayConnector()
		channel_cfg = {
			"channel_name": "Cloud Hub 1",
			"gateway_url": "https://gateway.mytra.money",
			"api_key": "sk-test-secret-api-key-12345",
		}

		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {
			"success": True,
			"message_id": "saas_tpl_1234",
		}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			res = connector.send_template(
				channel_cfg,
				to="+919830122891",
				template_name="order_confirmation",
				language_code="en_US",
			)
			self.assertTrue(res["success"])
			self.assertEqual(res["message_id"], "saas_tpl_1234")
			payload = mock_req.call_args.kwargs["json"]
			self.assertEqual(payload["type"], "template")
			self.assertEqual(payload["template"]["name"], "order_confirmation")

	def test_saas_gateway_verify_credentials(self):
		"""SaaSGatewayConnector verifies health and tenant connectivity."""
		connector = SaaSGatewayConnector()
		channel_cfg = {
			"channel_name": "Cloud Hub 1",
			"gateway_url": "https://gateway.mytra.money",
			"api_key": "sk-test-secret-api-key-12345",
		}

		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {
			"status": "healthy",
			"tier": "enterprise",
			"credits_remaining": 45000,
		}

		with patch.object(connector.session, "request", return_value=mock_resp):
			diag = connector.verify_credentials(channel_cfg)
			self.assertTrue(diag["success"])
			self.assertEqual(diag["status"], "healthy")

	def test_saas_gateway_auth_error_on_401(self):
		"""SaaSGatewayConnector raises WhatsAppAuthError on HTTP 401."""
		connector = SaaSGatewayConnector()
		channel_cfg = {
			"channel_name": "Cloud Hub 1",
			"gateway_url": "https://gateway.mytra.money",
			"api_key": "invalid_key",
		}

		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 401
		mock_resp.text = "Unauthorized"

		with patch.object(connector.session, "request", return_value=mock_resp):
			with self.assertRaises(WhatsAppAuthError):
				connector.send_text(channel_cfg, to="+919830122891", text="Test")

	def test_saas_gateway_credential_redaction(self):
		"""API keys are never exposed in exception strings."""
		connector = SaaSGatewayConnector()
		channel_cfg = {
			"channel_name": "Cloud Hub 1",
			"gateway_url": "https://gateway.mytra.money",
			"api_key": "sk-supersecretkey9999",
		}

		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 400
		mock_resp.text = "Error for sk-supersecretkey9999"
		mock_resp.json.return_value = {"error": {"message": "Error for sk-supersecretkey9999"}}

		with patch.object(connector.session, "request", return_value=mock_resp):
			with self.assertRaises(WhatsAppConnectorError) as ctx:
				connector.send_text(channel_cfg, to="+919830122891", text="Test")
			err_str = str(ctx.exception)
			self.assertNotIn("sk-supersecretkey9999", err_str)
			self.assertIn("sk-[REDACTED]", err_str)
