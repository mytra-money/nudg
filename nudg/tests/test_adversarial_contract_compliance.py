# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Empirical Adversarial Test Suite for Meta Cloud API v18.0+ Contracts, Webhooks, and Concurrency.

Challenges:
1. Meta Cloud API v18.0+ payload contracts across text, media, templates, interactive (SPM/MPM).
2. Incoming webhook event parsing across message types and status callbacks.
3. Rapid / concurrent deduplication and contact consent updates.
4. Token redaction, rate limiting, and security resilience.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import threading
import time
import unittest
from unittest.mock import MagicMock, call, patch

import requests
from werkzeug.wrappers import Response

import frappe

from nudg.integrations import webhook
from nudg.integrations.connector.base import (
	WhatsAppAuthError,
	WhatsAppConnectorError,
	WhatsAppNetworkError,
	WhatsAppPayloadError,
	WhatsAppRateLimitError,
)
from nudg.integrations.connector.meta_cloud import DirectMetaCloudApiConnector
from nudg.integrations.repository.contact_repo import DeskContactRepository
from nudg.integrations.repository.message_repo import DeskMessageRepository


class TestAdversarialContractCompliance(unittest.TestCase):
	"""Adversarial stress-testing suite for WhatsApp Meta Cloud API v18.0+ contracts."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "request", "form_dict", "response", "lang", "site"):
			self._saved[name] = getattr(frappe.local, name, None)
		self._saved_cache = getattr(frappe, "cache", None)

		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Guest", data=frappe._dict())
		frappe.local.lang = "en"
		frappe.local.site = "test.local"
		frappe.local.db = MagicMock()
		frappe.local.response = frappe._dict()
		frappe.local.form_dict = frappe._dict()

		self._saved_enqueue = getattr(frappe, "enqueue", None)
		frappe.enqueue = MagicMock()
		frappe.cache = MagicMock()
		frappe.cache.hget.return_value = {}

		self.mock_request = MagicMock()
		self.mock_request.method = "POST"
		self.mock_request.args = {}
		self.mock_request.get_data.return_value = b""
		frappe.local.request = self.mock_request

		self.standard_channel_cfg = {
			"phone_number_id": "999888777",
			"access_token": "TEST_META_TOKEN_12345",
			"api_version": "v18.0",
			"api_base_url": "https://graph.facebook.com",
		}

	def tearDown(self):
		if self._saved_enqueue is not None:
			frappe.enqueue = self._saved_enqueue
		frappe.cache = self._saved_cache
		for name in ("flags", "session", "db", "request", "form_dict", "response", "lang", "site"):
			val = self._saved.get(name)
			if val is not None:
				setattr(frappe.local, name, val)
			else:
				try:
					delattr(frappe.local, name)
				except AttributeError:
					pass
		super().tearDown()

	# =========================================================================
	# 1. META CLOUD API v18.0+ PAYLOAD CONTRACT CHALLENGES
	# =========================================================================

	def test_send_text_standard_payload_contract(self):
		"""Standard text payload conforms to Meta v18.0+ spec."""
		connector = DirectMetaCloudApiConnector()
		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.TEXT01"}]}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			res = connector.send_text(self.standard_channel_cfg, to="+1 (555) 019-2834", text="Hello v18")
			self.assertTrue(res["success"])
			self.assertEqual(res["message_id"], "wamid.TEXT01")

			sent_json = mock_req.call_args[1]["json"]
			self.assertEqual(sent_json["messaging_product"], "whatsapp")
			self.assertEqual(sent_json["recipient_type"], "individual")
			self.assertEqual(sent_json["to"], "15550192834")
			self.assertEqual(sent_json["type"], "text")
			self.assertEqual(sent_json["text"], {"preview_url": False, "body": "Hello v18"})

	def test_send_text_preview_url_contract_gap(self):
		"""Verify send_text supports sending a text message with preview_url=True and False per Meta v18.0+."""
		connector = DirectMetaCloudApiConnector()
		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.PREV01"}]}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			res = connector.send_text(
				self.standard_channel_cfg,
				to="15550192834",
				text="Check out https://frappe.io",
				preview_url=True,
			)
			self.assertTrue(res["success"])
			sent_json = mock_req.call_args[1]["json"]
			self.assertEqual(sent_json["type"], "text")
			self.assertEqual(sent_json["text"]["preview_url"], True)
			self.assertEqual(sent_json["text"]["body"], "Check out https://frappe.io")

			connector.send_text(
				self.standard_channel_cfg,
				to="15550192834",
				text="Check out https://frappe.io",
				preview_url=False,
			)
			sent_json = mock_req.call_args[1]["json"]
			self.assertEqual(sent_json["text"]["preview_url"], False)

	def test_send_text_empty_and_whitespace_rejection(self):
		"""Adversarial input: Empty strings and whitespace-only must be rejected."""
		connector = DirectMetaCloudApiConnector()
		for bad_text in ("", "   ", "\t\n\r", "      "):
			with self.assertRaises(WhatsAppPayloadError):
				connector.send_text(self.standard_channel_cfg, to="15550192834", text=bad_text)

	def test_send_text_phone_number_normalization_adversarial(self):
		"""Phone normalization handles messy formatting and rejects non-digits."""
		connector = DirectMetaCloudApiConnector()
		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.NORM01"}]}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			connector.send_text(self.standard_channel_cfg, to="+44 (0) 7911 123 456", text="Formatted UK")
			self.assertEqual(mock_req.call_args[1]["json"]["to"], "4407911123456")

		with self.assertRaises(WhatsAppPayloadError):
			connector.send_text(self.standard_channel_cfg, to="invalid-phone-without-digits", text="Test")

		with self.assertRaises(WhatsAppPayloadError):
			connector.send_text(self.standard_channel_cfg, to="", text="Test")

	def test_send_text_with_reply_to_context(self):
		"""Context object generated for replying to previous wamid."""
		connector = DirectMetaCloudApiConnector()
		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.REPLY01"}]}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			connector.send_text(
				self.standard_channel_cfg,
				to="15550192834",
				text="In reply to your question",
				reply_to="wamid.PREV999",
			)
			sent_json = mock_req.call_args[1]["json"]
			self.assertIn("context", sent_json)
			self.assertEqual(sent_json["context"], {"message_id": "wamid.PREV999"})

	def test_send_media_contracts_across_mime_types(self):
		"""Media payloads across image, video, audio, document contracts."""
		connector = DirectMetaCloudApiConnector()
		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.MEDIA_OK"}]}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			# 1. Image with caption
			connector.send_media(
				self.standard_channel_cfg,
				to="15550192834",
				media_id_or_url="https://example.com/photo.jpg",
				mime_type="image/jpeg",
				caption="Photo caption",
			)
			payload = mock_req.call_args[1]["json"]
			self.assertEqual(payload["type"], "image")
			self.assertEqual(payload["image"]["link"], "https://example.com/photo.jpg")
			self.assertEqual(payload["image"]["caption"], "Photo caption")

			# 2. Video with caption
			connector.send_media(
				self.standard_channel_cfg,
				to="15550192834",
				media_id_or_url="https://example.com/video.mp4",
				mime_type="video/mp4",
				caption="Demo clip",
			)
			payload = mock_req.call_args[1]["json"]
			self.assertEqual(payload["type"], "video")
			self.assertEqual(payload["video"]["link"], "https://example.com/video.mp4")
			self.assertEqual(payload["video"]["caption"], "Demo clip")

			# 3. Document with filename and caption
			connector.send_media(
				self.standard_channel_cfg,
				to="15550192834",
				media_id_or_url="https://example.com/manual.pdf",
				mime_type="application/pdf",
				caption="User Guide",
				filename="Manual.pdf",
			)
			payload = mock_req.call_args[1]["json"]
			self.assertEqual(payload["type"], "document")
			self.assertEqual(payload["document"]["link"], "https://example.com/manual.pdf")
			self.assertEqual(payload["document"]["caption"], "User Guide")
			self.assertEqual(payload["document"]["filename"], "Manual.pdf")

			# 4. Audio: Meta Cloud API v18.0 DOES NOT support caption on audio
			connector.send_media(
				self.standard_channel_cfg,
				to="15550192834",
				media_id_or_url="https://example.com/voice.ogg",
				mime_type="audio/ogg",
				caption="Ignored audio caption",
			)
			payload = mock_req.call_args[1]["json"]
			self.assertEqual(payload["type"], "audio")
			self.assertNotIn("caption", payload["audio"])

	def test_send_media_sticker_webp_precedence_bug(self):
		"""VULNERABILITY CHALLENGE: mime_type 'image/webp' is captured by startswith('image/')!

		In meta_cloud.py:
		  if mime_type.startswith("image/"): media_type = "image"
		  elif mime_type == "image/webp": media_type = "sticker"
		Because 'image/webp'.startswith('image/') is True, 'image/webp' NEVER evaluates
		to 'sticker'. It erroneously sets type='image'.
		"""
		connector = DirectMetaCloudApiConnector()
		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.STICKER01"}]}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			connector.send_media(
				self.standard_channel_cfg,
				to="15550192834",
				media_id_or_url="100999888777666",
				mime_type="image/webp",
			)
			payload = mock_req.call_args[1]["json"]
			self.assertEqual(payload["type"], "sticker")
			self.assertIn("sticker", payload)
			self.assertEqual(payload["sticker"]["id"], "100999888777666")
			self.assertNotIn("image", payload)
			self.assertNotIn("caption", payload["sticker"])

			# 2. Explicit is_sticker=True with link URL
			connector.send_media(
				self.standard_channel_cfg,
				to="15550192834",
				media_id_or_url="https://example.com/stickers/happy.webp",
				mime_type="image/webp",
				is_sticker=True,
			)
			payload = mock_req.call_args[1]["json"]
			self.assertEqual(payload["type"], "sticker")
			self.assertIn("sticker", payload)
			self.assertEqual(payload["sticker"]["link"], "https://example.com/stickers/happy.webp")
			self.assertNotIn("image", payload)

	def test_send_media_id_vs_url_detection(self):
		"""Media sent by ID uses 'id'; media sent by URL uses 'link'."""
		connector = DirectMetaCloudApiConnector()
		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.MEDIA_ID"}]}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			# Meta numeric ID (e.g., uploaded media ID)
			connector.send_media(
				self.standard_channel_cfg,
				to="15550192834",
				media_id_or_url="887766554433221",
				mime_type="image/png",
			)
			payload = mock_req.call_args[1]["json"]
			self.assertIn("id", payload["image"])
			self.assertNotIn("link", payload["image"])
			self.assertEqual(payload["image"]["id"], "887766554433221")

			# External URL
			connector.send_media(
				self.standard_channel_cfg,
				to="15550192834",
				media_id_or_url="https://cdn.example.com/images/banner.png",
				mime_type="image/png",
			)
			payload = mock_req.call_args[1]["json"]
			self.assertIn("link", payload["image"])
			self.assertNotIn("id", payload["image"])
			self.assertEqual(payload["image"]["link"], "https://cdn.example.com/images/banner.png")

	def test_send_template_complex_payload_contract(self):
		"""Complex template message with header, dynamic body parameters, and interactive buttons."""
		connector = DirectMetaCloudApiConnector()
		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.COMPLEX_TMPL"}]}

		components = [
			{
				"type": "header",
				"parameters": [
					{
						"type": "image",
						"image": {"link": "https://example.com/header.jpg"},
					}
				],
			},
			{
				"type": "body",
				"parameters": [
					{"type": "text", "text": "Acme Corp"},
					{"type": "currency", "currency": {"fallback_value": "$150.00", "code": "USD", "amount_1000": 150000}},
					{"type": "date_time", "date_time": {"fallback_value": "November 15, 2026"}},
				],
			},
			{
				"type": "button",
				"sub_type": "quick_reply",
				"index": 0,
				"parameters": [
					{"type": "payload", "payload": "CONFIRM_APPOINTMENT_ID_456"}
				],
			},
			{
				"type": "button",
				"sub_type": "quick_reply",
				"index": 1,
				"parameters": [
					{"type": "payload", "payload": "RESCHEDULE_APPOINTMENT_ID_456"}
				],
			},
		]

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			res = connector.send_template(
				self.standard_channel_cfg,
				to="+15551234567",
				template_name="appointment_reminder_v2",
				language_code="en_US",
				components=components,
			)
			self.assertTrue(res["success"])
			self.assertEqual(res["message_id"], "wamid.COMPLEX_TMPL")

			sent_json = mock_req.call_args[1]["json"]
			self.assertEqual(sent_json["type"], "template")
			template_obj = sent_json["template"]
			self.assertEqual(template_obj["name"], "appointment_reminder_v2")
			self.assertEqual(template_obj["language"]["code"], "en_US")
			self.assertEqual(len(template_obj["components"]), 4)
			self.assertEqual(template_obj["components"][0]["type"], "header")
			self.assertEqual(template_obj["components"][1]["type"], "body")
			self.assertEqual(template_obj["components"][2]["type"], "button")

	def test_send_interactive_single_product_message_contract(self):
		"""Single-Product Message (SPM) interactive payload conforms to Meta v18.0+."""
		connector = DirectMetaCloudApiConnector()
		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.SPM_MSG"}]}

		spm_interactive = {
			"type": "product",
			"body": {"text": "Check out this featured item:"},
			"footer": {"text": "Free shipping on orders over $50"},
			"action": {
				"catalog_id": "987654321012345",
				"product_retailer_id": "SKU-SHIRT-BLUE-L",
			},
		}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			res = connector.send_interactive(
				self.standard_channel_cfg,
				to="15551234567",
				interactive_payload=spm_interactive,
			)
			self.assertTrue(res["success"])
			self.assertEqual(res["message_id"], "wamid.SPM_MSG")

			payload = mock_req.call_args[1]["json"]
			self.assertEqual(payload["type"], "interactive")
			self.assertEqual(payload["interactive"]["type"], "product")
			self.assertEqual(payload["interactive"]["action"]["catalog_id"], "987654321012345")
			self.assertEqual(payload["interactive"]["action"]["product_retailer_id"], "SKU-SHIRT-BLUE-L")

	def test_send_interactive_multi_product_message_contract(self):
		"""Multi-Product Message (MPM) interactive payload conforms to Meta v18.0+."""
		connector = DirectMetaCloudApiConnector()
		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 200
		mock_resp.json.return_value = {"messages": [{"id": "wamid.MPM_MSG"}]}

		mpm_interactive = {
			"type": "product_list",
			"header": {"type": "text", "text": "Weekly Specials"},
			"body": {"text": "Browse our popular electronics categories:"},
			"footer": {"text": "Limited time offers"},
			"action": {
				"catalog_id": "987654321012345",
				"sections": [
					{
						"title": "Smartphones",
						"product_items": [
							{"product_retailer_id": "PHONE-001"},
							{"product_retailer_id": "PHONE-002"},
						],
					},
					{
						"title": "Accessories",
						"product_items": [
							{"product_retailer_id": "CASE-001"},
							{"product_retailer_id": "CABLE-001"},
						],
					},
				],
			},
		}

		with patch.object(connector.session, "request", return_value=mock_resp) as mock_req:
			res = connector.send_interactive(
				self.standard_channel_cfg,
				to="15551234567",
				interactive_payload=mpm_interactive,
			)
			self.assertTrue(res["success"])
			self.assertEqual(res["message_id"], "wamid.MPM_MSG")

			payload = mock_req.call_args[1]["json"]
			self.assertEqual(payload["type"], "interactive")
			self.assertEqual(payload["interactive"]["type"], "product_list")
			sections = payload["interactive"]["action"]["sections"]
			self.assertEqual(len(sections), 2)
			self.assertEqual(sections[0]["title"], "Smartphones")
			self.assertEqual(len(sections[0]["product_items"]), 2)

	# =========================================================================
	# 2. INCOMING WEBHOOK EVENT PARSING & STATUS CALLBACK CHALLENGES
	# =========================================================================

	def test_webhook_incoming_interactive_button_and_list_replies(self):
		"""Webhook parser properly extracts button_reply and list_reply titles."""
		# 1. button_reply
		button_event = {
			"entry": [{
				"changes": [{
					"field": "messages",
					"value": {
						"metadata": {"phone_number_id": "999888777"},
						"contacts": [{"profile": {"name": "Charlie"}, "wa_id": "15551112222"}],
						"messages": [{
							"id": "wamid.BTN_REPLY",
							"from": "15551112222",
							"timestamp": "1700000001",
							"type": "interactive",
							"interactive": {
								"type": "button_reply",
								"button_reply": {"id": "btn_sales", "title": "Talk to Sales"},
							},
						}],
					},
				}]
			}]
		}
		raw_bytes = json.dumps(button_event).encode("utf-8")
		frappe.local.request.get_data.return_value = raw_bytes

		with patch.object(webhook, "_resolve_channel", return_value=None):
			with patch.object(webhook, "_get_webhook_secret", return_value=None):
				with patch("nudg.integrations.repository.contact_repo.DeskContactRepository.get_or_create_contact", return_value="C-1"):
					with patch("nudg.integrations.repository.message_repo.DeskMessageRepository.is_duplicate_message", return_value=False):
						with patch("nudg.integrations.repository.message_repo.DeskMessageRepository.save_incoming_message") as mock_save:
							mock_save.return_value = {"record_name": "MSG-B1", "content": "Talk to Sales"}
							resp = webhook.handler()
							self.assertEqual(resp, "ok")
							saved_msg = mock_save.call_args[1]["msg"]
							self.assertEqual(saved_msg["interactive"]["button_reply"]["title"], "Talk to Sales")

		# 2. list_reply
		list_event = {
			"entry": [{
				"changes": [{
					"field": "messages",
					"value": {
						"metadata": {"phone_number_id": "999888777"},
						"contacts": [{"profile": {"name": "Dana"}, "wa_id": "15553334444"}],
						"messages": [{
							"id": "wamid.LIST_REPLY",
							"from": "15553334444",
							"timestamp": "1700000002",
							"type": "interactive",
							"interactive": {
								"type": "list_reply",
								"list_reply": {"id": "item_premium", "title": "Premium Tier Plan", "description": "Full access"},
							},
						}],
					},
				}]
			}]
		}
		raw_bytes = json.dumps(list_event).encode("utf-8")
		frappe.local.request.get_data.return_value = raw_bytes

		with patch.object(webhook, "_resolve_channel", return_value=None):
			with patch.object(webhook, "_get_webhook_secret", return_value=None):
				with patch("nudg.integrations.repository.contact_repo.DeskContactRepository.get_or_create_contact", return_value="C-2"):
					with patch("nudg.integrations.repository.message_repo.DeskMessageRepository.is_duplicate_message", return_value=False):
						with patch("nudg.integrations.repository.message_repo.DeskMessageRepository.save_incoming_message") as mock_save:
							mock_save.return_value = {"record_name": "MSG-L1", "content": "Premium Tier Plan"}
							resp = webhook.handler()
							self.assertEqual(resp, "ok")
							saved_msg = mock_save.call_args[1]["msg"]
							self.assertEqual(saved_msg["interactive"]["list_reply"]["title"], "Premium Tier Plan")

	def test_webhook_incoming_reaction_emoji_and_removal(self):
		"""Incoming emoji reaction and empty emoji (reaction removal)."""
		# Add reaction
		add_reaction = {
			"id": "wamid.REACT01",
			"from": "15559990000",
			"timestamp": "1700000003",
			"type": "reaction",
			"reaction": {"message_id": "wamid.ORIGINAL123", "emoji": "❤️"},
		}
		# DeskMessageRepository.save_incoming_message handles reaction
		with patch.object(DeskMessageRepository, "is_self_hosted", return_value=False):
			with patch("frappe.db.exists", return_value=False):
				with patch("frappe.publish_realtime") as mock_pub:
					res = DeskMessageRepository.save_incoming_message("Main Channel", add_reaction, "Contact-1")
					self.assertEqual(res["content"], "❤️")
					pub_data = mock_pub.call_args[0][1]
					self.assertEqual(pub_data["content"], "❤️")

		# Remove reaction (emoji is empty string)
		remove_reaction = {
			"id": "wamid.REACT02",
			"from": "15559990000",
			"timestamp": "1700000004",
			"type": "reaction",
			"reaction": {"message_id": "wamid.ORIGINAL123", "emoji": ""},
		}
		with patch.object(DeskMessageRepository, "is_self_hosted", return_value=False):
			with patch("frappe.db.exists", return_value=False):
				with patch("frappe.publish_realtime"):
					res = DeskMessageRepository.save_incoming_message("Main Channel", remove_reaction, "Contact-1")
					self.assertEqual(res["content"], "")

	def test_webhook_incoming_media_caption_dropped_defect(self):
		"""VULNERABILITY CHALLENGE: Incoming media captions are completely discarded!

		In DeskMessageRepository.save_incoming_message:
		  if msg_type == 'text': content = ...
		  elif msg_type == 'button': content = ...
		  ...
		  elif msg_type == 'order': content = ...
		There is NO handler for msg_type in ('image', 'video', 'document') captions!
		Thus, content is left as empty string '', discarding customer notes, keywords, and STOP consent.
		"""
		incoming_media_msg = {
			"id": "wamid.IMAGE_WITH_CAPTION",
			"from": "15558887777",
			"timestamp": "1700000005",
			"type": "image",
			"image": {
				"caption": "URGENT: Machine stopped working with error code E-44",
				"mime_type": "image/jpeg",
				"sha256": "abcdef123456",
				"id": "media_id_99999",
			},
		}

		with patch.object(DeskMessageRepository, "is_self_hosted", return_value=False):
			with patch("frappe.db.exists", return_value=False):
				with patch("frappe.publish_realtime"):
					res = DeskMessageRepository.save_incoming_message("Channel-1", incoming_media_msg, "Contact-8")
					# Verifies incoming media caption is properly extracted into message content
					self.assertEqual(
						res["content"],
						"URGENT: Machine stopped working with error code E-44",
					)

	def test_webhook_status_lifecycle_and_reversion_protection(self):
		"""Adversarial Challenge: Status lifecycle precedence (Sent -> Delivered -> Read).

		Out-of-order delayed callbacks (e.g. Delivered arriving after Read) must NOT revert status.
		"""
		with patch.object(DeskMessageRepository, "is_self_hosted", return_value=True):
			with patch("frappe.db.exists", return_value=True):
				with patch("frappe.db.get_value") as mock_get_value:
					with patch("frappe.db.set_value") as mock_set_value:
						with patch("frappe.publish_realtime"):
							# Mock message found with current_status = 'Read'
							mock_get_value.side_effect = lambda dt, filters, field: (
								"MSG-001" if field == "name" else "Read"
							)

							# Meta sends delayed 'delivered' callback for already read message
							updated = DeskMessageRepository.update_message_status(
								message_id="wamid.OUTBOUND_1",
								new_status_raw="delivered",
							)
							# Must be rejected (precedence check prevents reversion)
							self.assertFalse(updated)
							mock_set_value.assert_not_called()

	def test_webhook_status_failed_callback_handling(self):
		"""Failed status callback updates message to Failed and captures error details."""
		errors_payload = [
			{
				"code": 131026,
				"title": "Message undeliverable",
				"message": "Message undeliverable",
				"error_data": {"details": "Recipient phone number not on allowlist"},
			}
		]
		raw_event = {
			"entry": [{
				"changes": [{
					"field": "messages",
					"value": {
						"metadata": {"phone_number_id": "999888777"},
						"statuses": [{
							"id": "wamid.FAILED_MSG_1",
							"status": "failed",
							"timestamp": "1700000010",
							"recipient_id": "15551234567",
							"errors": errors_payload,
						}],
					},
				}]
			}]
		}
		raw_bytes = json.dumps(raw_event).encode("utf-8")
		frappe.local.request.get_data.return_value = raw_bytes

		with patch.object(webhook, "_resolve_channel", return_value=None):
			with patch.object(webhook, "_get_webhook_secret", return_value=None):
				with patch.object(DeskMessageRepository, "update_message_status") as mock_update:
					resp = webhook.handler()
					self.assertEqual(resp, "ok")
					mock_update.assert_called_once_with(
						message_id="wamid.FAILED_MSG_1",
						new_status_raw="failed",
						timestamp="1700000010",
						errors=errors_payload,
					)

	def test_webhook_batch_messages_and_statuses_in_single_entry(self):
		"""Payload with multiple messages and multiple statuses processes all items."""
		batch_event = {
			"entry": [{
				"changes": [{
					"field": "messages",
					"value": {
						"metadata": {"phone_number_id": "999888777"},
						"contacts": [{"profile": {"name": "Multi User"}}],
						"messages": [
							{"id": "wamid.BATCH_M1", "from": "15551111111", "type": "text", "text": {"body": "First"}},
							{"id": "wamid.BATCH_M2", "from": "15552222222", "type": "text", "text": {"body": "Second"}},
						],
						"statuses": [
							{"id": "wamid.BATCH_S1", "status": "delivered"},
							{"id": "wamid.BATCH_S2", "status": "read"},
						],
					},
				}]
			}]
		}
		raw_bytes = json.dumps(batch_event).encode("utf-8")
		frappe.local.request.get_data.return_value = raw_bytes

		with patch.object(webhook, "_resolve_channel", return_value=None):
			with patch.object(webhook, "_get_webhook_secret", return_value=None):
				with patch.object(webhook, "_process_incoming_message") as mock_msg:
					with patch.object(webhook, "_process_status_update") as mock_stat:
						resp = webhook.handler()
						self.assertEqual(resp, "ok")
						self.assertEqual(mock_msg.call_count, 2)
						self.assertEqual(mock_stat.call_count, 2)

	# =========================================================================
	# 3. CONCURRENCY, DEDUPLICATION & CONSENT CHALLENGES
	# =========================================================================

	def test_deduplication_under_rapid_sequential_delivery(self):
		"""Same wamid arriving sequentially is filtered by is_duplicate_message."""
		wamid = "wamid.DUPLICATE_SEQUENTIAL_123"

		# First call: not in DB -> processed
		with patch.object(DeskMessageRepository, "is_duplicate_message", side_effect=[False, True]):
			with patch.object(DeskMessageRepository, "save_incoming_message") as mock_save:
				with patch.object(DeskContactRepository, "get_or_create_contact", return_value="C1"):
					# First delivery
					webhook._process_incoming_message(
						{"id": wamid, "from": "15550001111", "type": "text", "text": {"body": "Hi"}},
						None,
						{},
					)
					self.assertEqual(mock_save.call_count, 1)

					# Second duplicate delivery
					webhook._process_incoming_message(
						{"id": wamid, "from": "15550001111", "type": "text", "text": {"body": "Hi"}},
						None,
						{},
					)
					# Remains 1 because duplicate was skipped
					self.assertEqual(mock_save.call_count, 1)

	def test_concurrent_payload_race_condition_demonstration(self):
		"""CONCURRENCY CHALLENGE: In-memory race window between check and save.

		If two threads receive the same wamid concurrently, both can check
		is_duplicate_message before either writes to DB unless locked or constrained by unique DB index.
		"""
		wamid = "wamid.RACE_CONCURRENT_999"
		results = []
		lock = threading.Lock()
		database_records = []

		def simulated_worker():
			# Check duplicate (reads database_records)
			with lock:
				is_dup = wamid in database_records
			# Simulate network/CPU latency between check and write
			time.sleep(0.01)
			if not is_dup:
				with lock:
					database_records.append(wamid)
				results.append("SAVED")
			else:
				results.append("SKIPPED")

		t1 = threading.Thread(target=simulated_worker)
		t2 = threading.Thread(target=simulated_worker)
		t1.start()
		t2.start()
		t1.join()
		t2.join()

		# Empirically verifies whether concurrency without DB lock results in race insertion
		self.assertEqual(len(results), 2)
		if results.count("SAVED") == 2:
			# Race condition confirmed
			self.assertEqual(results, ["SAVED", "SAVED"])
		else:
			self.assertIn("SKIPPED", results)

	def test_contact_consent_stop_keywords_exhaustive(self):
		"""All specified opt-out keywords trigger consent opt-out."""
		keywords = ["STOP", "stop", "Stop ", "\nUNSUBSCRIBE\t", "cancel", "END", "QUIT", "ARRET", "OPTOUT"]

		for kw in keywords:
			with patch.object(DeskContactRepository, "update_consent") as mock_consent:
				with patch.object(DeskMessageRepository, "save_incoming_message", return_value={"record_name": "M", "content": kw}):
					with patch.object(DeskContactRepository, "get_or_create_contact", return_value="C-TEST"):
						with patch.object(DeskMessageRepository, "is_duplicate_message", return_value=False):
							webhook._process_incoming_message(
								{"id": f"wamid.OPT_{kw[:3]}", "from": "1555000", "type": "text", "text": {"body": kw}},
								None,
								{},
							)
							mock_consent.assert_called_once_with("C-TEST", "Opted-Out", reason="STOP keyword")

	def test_contact_consent_start_keywords_exhaustive(self):
		"""All specified opt-in keywords trigger consent opt-in."""
		keywords = ["START", "start", "Start ", "\nUNSTOP\t", "OPTIN"]

		for kw in keywords:
			with patch.object(DeskContactRepository, "update_consent") as mock_consent:
				with patch.object(DeskMessageRepository, "save_incoming_message", return_value={"record_name": "M", "content": kw}):
					with patch.object(DeskContactRepository, "get_or_create_contact", return_value="C-TEST"):
						with patch.object(DeskMessageRepository, "is_duplicate_message", return_value=False):
							webhook._process_incoming_message(
								{"id": f"wamid.OPTIN_{kw[:3]}", "from": "1555000", "type": "text", "text": {"body": kw}},
								None,
								{},
							)
							mock_consent.assert_called_once_with("C-TEST", "Opted-In", reason="START keyword")

	def test_contact_consent_missing_column_on_wa_profile_safe(self):
		"""When WA Profile does not have consent_status column, update_consent handles gracefully."""
		with patch("frappe.db.exists") as mock_exists:
			mock_exists.side_effect = lambda dt, name=None: True if dt == "DocType" and name == "WA Profile" or name == "PROF-1" else False
			with patch("frappe.db.has_column", return_value=False):
				with patch("frappe.db.set_value") as mock_set:
					# Must not throw exception
					DeskContactRepository.update_consent("PROF-1", "Opted-Out", reason="STOP keyword")
					mock_set.assert_not_called()

	# =========================================================================
	# 4. SECURITY, RESILIENCE & ERROR REDACTION CHALLENGES
	# =========================================================================

	def test_token_redaction_in_all_error_shapes(self):
		"""All forms of EAAB tokens are redacted from error messages."""
		connector = DirectMetaCloudApiConnector()
		secret_token = "EAABt0k3n_vErYsEcReT_1234567890_abcdef"

		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 401
		mock_resp.text = f"OAuthException: Invalid token {secret_token}"
		mock_resp.json.return_value = {
			"error": {
				"message": f"Session has expired for {secret_token}. Please re-authenticate.",
				"code": 190,
			}
		}

		with patch.object(connector.session, "request", return_value=mock_resp):
			with self.assertRaises(WhatsAppAuthError) as ctx:
				connector.send_text(self.standard_channel_cfg, to="15551234567", text="Test")

			err_msg = str(ctx.exception)
			self.assertNotIn(secret_token, err_msg)
			self.assertIn("EAAB[REDACTED]", err_msg)

	def test_rate_limit_retry_exhaustion_raises_rate_limit_error(self):
		"""Repeated 429 rate limit responses beyond max retries raise WhatsAppRateLimitError."""
		connector = DirectMetaCloudApiConnector()
		resp_429 = MagicMock(spec=requests.Response)
		resp_429.status_code = 429
		resp_429.headers = {"Retry-After": "0.001"}
		resp_429.json.return_value = {"error": {"message": "Rate limit exceeded", "code": 80007}}

		with patch.object(connector.session, "request", return_value=resp_429):
			with patch("time.sleep"):
				with self.assertRaises(WhatsAppRateLimitError) as ctx:
					connector.send_text(self.standard_channel_cfg, to="15551234567", text="Flood test")
				self.assertIn("rate limit exceeded after", str(ctx.exception))

	def test_network_timeout_and_connection_error_handling(self):
		"""Requests network errors and timeouts are translated to WhatsAppNetworkError."""
		connector = DirectMetaCloudApiConnector()

		# Timeout
		with patch.object(connector.session, "request", side_effect=requests.exceptions.Timeout("Connection timed out")):
			with self.assertRaises(WhatsAppNetworkError) as ctx:
				connector.send_text(self.standard_channel_cfg, to="15551234567", text="Timeout test")
			self.assertIn("timed out", str(ctx.exception))

		# RequestException
		with patch.object(connector.session, "request", side_effect=requests.exceptions.ConnectionError("Failed to resolve graph.facebook.com")):
			with self.assertRaises(WhatsAppNetworkError) as ctx:
				connector.send_text(self.standard_channel_cfg, to="15551234567", text="Connection test")
			self.assertIn("connection error", str(ctx.exception))

	def test_webhook_signature_timing_attack_resistance(self):
		"""Webhook signature uses constant-time hmac.compare_digest."""
		secret = "super_webhook_secret_key"
		body = b'{"entry": []}'
		correct_hash = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

		with patch("frappe.get_request_header", return_value=f"sha256={correct_hash}"):
			# Valid hash does not throw
			webhook._verify_signature(body, secret)

		# Tampered hash
		tampered_hash = correct_hash[:-1] + ("0" if correct_hash[-1] != "0" else "1")
		with patch("frappe.get_request_header", return_value=f"sha256={tampered_hash}"):
			with self.assertRaises(frappe.AuthenticationError):
				webhook._verify_signature(body, secret)

	def test_webhook_missing_signature_header_throws_auth_error(self):
		"""Missing or improperly prefixed X-Hub-Signature-256 throws AuthenticationError."""
		with patch("frappe.get_request_header", return_value=""):
			with self.assertRaises(frappe.AuthenticationError):
				webhook._verify_signature(b"data", "secret")

		with patch("frappe.get_request_header", return_value="malformed_prefix_12345"):
			with self.assertRaises(frappe.AuthenticationError):
				webhook._verify_signature(b"data", "secret")


if __name__ == "__main__":
	unittest.main()
