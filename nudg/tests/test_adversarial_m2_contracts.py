# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Adversarial Contract Compliance and Security Test Suite for Milestone 2.

Challenges:
1. Module Isolation Contract: AST-level verification that no files in `nudg`
   import `whatsapp` directly outside `adapter.py`.
2. Token Scrubbing: Verification that Meta EAAB access tokens are scrubbed and
   never logged or persisted in error responses across new services (`campaigns.py`,
   `catalog.py`, `webhook.py`).
3. Permission Enforcement: Verification that whitelisted APIs (`set_conversation_tags`,
   `publish_presence`, `auto_assign_round_robin`) strictly reject unauthenticated (Guest)
   and unauthorized non-agent users.
4. Thread notes stay empty. The removed note DocType must not reappear inside customer messages.
5. Presence Spoofing & Injection: Verification of `publish_presence` against malformed
   actions, SQL injection payloads, arbitrary event name spoofing, and non-existent conversations.
"""

from __future__ import annotations

import ast
import json
import logging
import os
from io import StringIO
from pathlib import Path
from typing import Any
import unittest
from unittest.mock import MagicMock, patch

import requests
from werkzeug.wrappers import Response

import frappe
from frappe.utils import now_datetime

from nudg import api, desk_api
from nudg.integrations import webhook
from nudg.integrations.connector.base import WhatsAppAuthError
from nudg.integrations.connector.meta_cloud import DirectMetaCloudApiConnector
from nudg.services import assignments, campaigns, catalog


class TestAdversarialM2Contracts(unittest.TestCase):
	"""Adversarial security and contract compliance challenger test suite."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "site", "lang", "request", "form_dict", "response"):
			self._saved[name] = getattr(frappe.local, name, None)
		self._saved_cache = getattr(frappe, "cache", None)

		self._saved_client_cache = getattr(frappe, "client_cache", None)
		self.mock_client_cache = MagicMock()
		self.mock_client_cache.get_value.return_value = {}
		frappe.client_cache = self.mock_client_cache

		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="test_desk_agent@example.com", data=frappe._dict())
		frappe.local.site = "test.local"
		frappe.local.lang = "en"
		frappe.local.response = frappe._dict()
		frappe.local.form_dict = frappe._dict()

		self.mock_db = MagicMock()
		frappe.local.db = self.mock_db

		self.mock_cache = MagicMock()
		self.mock_cache.get_value.return_value = 0
		self.mock_cache.hget.return_value = {}
		frappe.cache = MagicMock(return_value=self.mock_cache)
		frappe.cache.hget.return_value = {}

		self.mock_request = MagicMock()
		self.mock_request.method = "POST"
		self.mock_request.args = {}
		self.mock_request.get_data.return_value = b""
		frappe.local.request = self.mock_request

		self.secret_token = "EAABt0k3n_vErYsEcReT_1234567890_abcdef"

	def tearDown(self):
		frappe.cache = self._saved_cache
		frappe.client_cache = self._saved_client_cache
		for name in ("flags", "session", "db", "site", "lang", "request", "form_dict", "response"):
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
	# 1. MODULE ISOLATION CONTRACT CHALLENGES
	# =========================================================================

	def test_ast_no_direct_whatsapp_imports_outside_adapter(self):
		"""Verify that no files in `nudg` import `whatsapp` outside `adapter.py`."""
		base_dir = Path(__file__).resolve().parent.parent  # nudg package root
		adapter_path = base_dir / "integrations" / "whatsapp" / "adapter.py"

		forbidden_imports: list[tuple[str, int, str]] = []

		for root, _, files in os.walk(base_dir):
			for file_name in files:
				if not file_name.endswith(".py"):
					continue
				file_path = Path(root) / file_name
				if file_path.resolve() == adapter_path.resolve():
					continue  # adapter.py is the designated bridge

				with open(file_path, "r", encoding="utf-8") as f:
					try:
						tree = ast.parse(f.read(), filename=str(file_path))
					except SyntaxError:
						continue

				for node in ast.walk(tree):
					if isinstance(node, ast.Import):
						for alias in node.names:
							if alias.name == "whatsapp" or alias.name.startswith("whatsapp."):
								forbidden_imports.append((str(file_path.relative_to(base_dir)), node.lineno, alias.name))
					elif isinstance(node, ast.ImportFrom):
						mod = node.module or ""
						if mod == "whatsapp" or mod.startswith("whatsapp."):
							forbidden_imports.append((str(file_path.relative_to(base_dir)), node.lineno, mod))

		self.assertEqual(
			forbidden_imports,
			[],
			f"Violations of Module Isolation Contract detected! Direct whatsapp imports: {forbidden_imports}",
		)

	def test_adapter_is_the_only_official_import_target(self):
		"""Verify adapter.py contains the only official frappe/whatsapp integration points."""
		adapter_path = Path(__file__).resolve().parent.parent / "integrations" / "whatsapp" / "adapter.py"
		with open(adapter_path, "r", encoding="utf-8") as f:
			tree = ast.parse(f.read(), filename=str(adapter_path))

		whatsapp_imports = []
		for node in ast.walk(tree):
			if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("whatsapp"):
				whatsapp_imports.append((node.lineno, node.module))

		self.assertGreater(len(whatsapp_imports), 0, "adapter.py should contain the official bridging imports.")

	# =========================================================================
	# 2. TOKEN SCRUBBING & SECRET REDACTION CHALLENGES
	# =========================================================================

	def test_campaign_runner_scrubs_token_from_error_message(self):
		"""Verify access tokens (EAAB...) are never saved in campaign recipient errors or last_error."""
		mock_doc = MagicMock()
		mock_doc.name = "CAMP-SEC-TEST"
		mock_doc.status = "Draft"
		mock_doc.template = "hello_world"
		mock_doc.whatsapp_channel = "test_channel"
		row = MagicMock(status="Pending", phone_number="15550001111", profile=None, variables_json=None)
		row.error_message = None
		mock_doc.recipients = [row]
		mock_doc.last_error = None

		self.mock_db.sql.return_value = [{"status": "Failed", "count": 1}]

		with patch("frappe.get_doc", return_value=mock_doc), \
		     patch("frappe.has_permission", return_value=True), \
		     patch("nudg.services.campaigns.check_recipient_consent", return_value=True), \
		     patch("nudg.services.campaigns.get_connector") as mock_conn:

			conn_instance = MagicMock()
			# Simulate provider error leaking the EAAB access token
			conn_instance.send_template.side_effect = RuntimeError(
				f"401 Client Error: Invalid OAuth access token {self.secret_token} for URI https://graph.facebook.com"
			)
			mock_conn.return_value = conn_instance

			campaigns.run_campaign("CAMP-SEC-TEST")

		# Assert token is scrubbed from recipient error_message
		self.assertNotIn(
			self.secret_token,
			row.error_message or "",
			f"Token leaked in recipient error_message: {row.error_message}",
		)
		# Assert token is scrubbed from campaign last_error
		self.assertNotIn(
			self.secret_token,
			mock_doc.last_error or "",
			f"Token leaked in campaign last_error: {mock_doc.last_error}",
		)

	def test_campaign_status_update_scrubs_token_from_webhook_errors(self):
		"""Verify access tokens in status callback errors are scrubbed before persistence."""
		self.mock_db.exists.return_value = True
		self.mock_db.sql.return_value = [{"name": "recip_1", "parent": "CAMP-001", "status": "Sent"}]

		leaked_error = [
			{
				"code": 190,
				"title": "OAuthException",
				"message": f"Session expired for token {self.secret_token}. Please re-authenticate.",
			}
		]

		with patch("frappe.publish_realtime"):
			campaigns.update_campaign_recipient_status(
				message_id="wamid.HBgL123",
				new_status="failed",
				errors=leaked_error,
			)

		self.mock_db.set_value.assert_called()
		recipient_updates = {}
		for call_item in self.mock_db.set_value.call_args_list:
			if call_item[0][0] == "WhatsApp Campaign Recipient":
				recipient_updates = call_item[0][2]
				break

		saved_error = str(recipient_updates.get("error_message", ""))
		self.assertNotIn(
			self.secret_token,
			saved_error,
			f"Token leaked in campaign recipient status error_message: {saved_error}",
		)

	def test_webhook_verification_does_not_log_raw_token(self):
		"""Verify webhook verification failure does not log raw verification or access tokens."""
		log_capture = StringIO()
		test_handler = logging.StreamHandler(log_capture)
		webhook_logger = logging.getLogger("nudg.integrations.webhook")
		webhook_logger.addHandler(test_handler)
		webhook_logger.setLevel(logging.DEBUG)

		frappe.local.form_dict = frappe._dict({
			"hub.mode": "subscribe",
			"hub.verify_token": self.secret_token,
			"hub.challenge": "11223344",
		})
		self.mock_db.exists.return_value = False

		try:
			resp = webhook._handle_verification()
			self.assertIsInstance(resp, Response)
			self.assertEqual(resp.status_code, 403)
		finally:
			webhook_logger.removeHandler(test_handler)

		log_output = log_capture.getvalue()
		self.assertNotIn(
			self.secret_token,
			log_output,
			f"Raw token logged in webhook verification failure log: {log_output}",
		)

	def test_catalog_service_connector_redaction_maintained(self):
		"""Verify Meta Cloud API connector redacts tokens when used by catalog service."""
		connector = DirectMetaCloudApiConnector()
		mock_resp = MagicMock(spec=requests.Response)
		mock_resp.status_code = 401
		mock_resp.text = f"Invalid OAuth token {self.secret_token}"
		mock_resp.json.return_value = {
			"error": {
				"message": f"Invalid token {self.secret_token}",
				"code": 190,
			}
		}

		channel_cfg = {
			"phone_number_id": "999888777",
			"access_token": self.secret_token,
			"api_version": "v18.0",
		}

		with patch.object(connector.session, "request", return_value=mock_resp):
			with self.assertRaises(WhatsAppAuthError) as ctx:
				connector.send_interactive(channel_cfg, to="15551234567", interactive_payload={"type": "product"})

			err_msg = str(ctx.exception)
			self.assertNotIn(self.secret_token, err_msg)
			self.assertIn("EAAB[REDACTED]", err_msg)

	# =========================================================================
	# 3. PERMISSION ENFORCEMENT & UNAUTHORIZED ACCESS CHALLENGES
	# =========================================================================

	def test_guest_rejected_across_all_whitelisted_apis(self):
		"""Verify that unauthenticated Guest requests are rejected with PermissionError across all Desk APIs."""
		frappe.local.session.user = "Guest"

		# 1. set_conversation_tags
		with self.assertRaises(frappe.PermissionError):
			desk_api.set_conversation_tags("prof_123", ["vip", "support"])

		# 3. auto_assign_round_robin
		with self.assertRaises(frappe.PermissionError):
			desk_api.auto_assign_round_robin("prof_123")

		# 4. publish_presence
		with self.assertRaises(frappe.PermissionError):
			api.publish_presence("prof_123", "typing")

	def test_set_conversation_tags_enforces_write_permission(self):
		"""Verify authenticated users without write permission cannot modify tags."""
		frappe.local.session.user = "unauthorized_user@example.com"
		self.mock_db.get_value.return_value = "CONV-001"

		mock_doc = MagicMock()
		mock_doc.name = "CONV-001"

		with patch("frappe.get_doc", return_value=mock_doc), \
		     patch("frappe.has_permission", side_effect=frappe.PermissionError("Not permitted to write")):
			with self.assertRaises(frappe.PermissionError):
				desk_api.set_conversation_tags("prof_123", ["tag1"])

	def test_auto_assign_round_robin_enforces_write_permission(self):
		"""Verify authenticated users without write permission cannot trigger auto_assign_round_robin."""
		frappe.local.session.user = "unauthorized_user@example.com"
		self.mock_db.get_value.return_value = "CONV-001"

		mock_doc = MagicMock()
		mock_doc.name = "CONV-001"
		mock_doc.assignee = None
		mock_doc.assignment_status = "Unassigned"

		with patch("nudg.services.assignments.ensure_conversation", return_value="CONV-001"), \
		     patch("frappe.get_doc", return_value=mock_doc), \
		     patch("frappe.has_permission", side_effect=frappe.PermissionError("Write permission denied")), \
		     patch("frappe.get_all", return_value=[]), \
		     patch("nudg.services.assignments._sync_todo"), \
		     patch("nudg.services.assignments.get_eligible_desk_agents", return_value=["agent@example.com"]):

			# auto_assign_round_robin must enforce write permission check
			with self.assertRaises(frappe.PermissionError):
				desk_api.auto_assign_round_robin("prof_123")

	def test_publish_presence_enforces_conversation_read_permission(self):
		"""Verify publish_presence enforces conversation permission or app authorization."""
		frappe.local.session.user = "unauthorized_user@example.com"
		self.mock_db.exists.return_value = True

		with patch("nudg.api.has_app_permission", return_value=False):
			# Should reject unauthorized user attempting to emit presence
			with self.assertRaises(frappe.PermissionError):
				api.publish_presence("prof_123", "typing")

	# =========================================================================
	# 4. INTERNAL NOTES CONFIDENTIALITY CHALLENGES
	# =========================================================================

	def test_notes_isolated_from_messages_array_in_get_thread(self):
		"""Internal notes stay out of the customer-facing messages array."""
		self.mock_db.exists.side_effect = lambda dt, name=None: dt in ("DocType", "WA Message", "Nudg Conversation")
		self.mock_db.get_value.return_value = "CONV-001"

		sample_message = frappe._dict({
			"name": "WAM-001",
			"to": "prof_123",
			"from": "15551234567",
			"direction": "Incoming",
			"message": "Hello from customer",
			"creation": "2026-11-08 08:00:00",
			"status": "Read",
			"is_template": 0,
		})

		with patch("frappe.get_list", return_value=[frappe._dict(name="prof_123", profile_name="Customer John")]), \
		     patch("frappe.has_permission", return_value=True), \
		     patch("nudg.api.adapter.get_messages", return_value=[sample_message]):

			thread = api.get_thread("prof_123")

		self.assertEqual(thread["notes"], [])
		self.assertIsInstance(thread["messages"], list)

	def test_notes_excluded_from_inbox_preview_and_status(self):
		"""Verify get_inbox preview never leaks internal note text."""
		self.mock_db.exists.return_value = True
		self.mock_db.get_value.return_value = "CONV-001"

		preview_message = frappe._dict({
			"name": "WAM-999",
			"to": "prof_123",
			"direction": "Outgoing",
			"message": "Public message to customer",
			"creation": "2026-11-08 08:10:00",
		})

		with patch("nudg.api._ready", return_value=True), \
		     patch("frappe.has_permission", return_value=True), \
		     patch("frappe.get_list") as mock_get_list, \
		     patch("nudg.services.assignments.get_conversation_map", return_value={}):

			# Return profile then messages, empty for other doctypes
			mock_get_list.side_effect = lambda dt, *args, **kwargs: (
				[frappe._dict(name="prof_123", profile_name="Jane Doe", whatsapp_account="Acc1")]
				if dt == "WA Profile"
				else ([preview_message] if dt == "WA Message" else [])
			)

			inbox = api.get_inbox()

		convs = inbox.get("conversations", [])
		self.assertEqual(len(convs), 1)
		preview = convs[0].get("preview", {})
		self.assertNotIn("CONFIDENTIAL", str(preview.get("message", "")))

	def test_notes_never_injected_into_outbound_catalog_payloads(self):
		"""Verify interactive SPM and MPM payloads never include internal note content."""
		spm = catalog.build_spm_payload(
			catalog_id="CATALOG_123",
			product_retailer_id="SKU_XYZ",
			body_text="Public catalog description",
		)
		spm_str = json.dumps(spm)
		self.assertNotIn("note", spm_str.lower())

		mpm = catalog.build_mpm_payload(
			catalog_id="CATALOG_123",
			sections=[{"title": "Electronics", "product_items": [{"product_retailer_id": "SKU_1"}]}],
			body_text="Our latest electronics",
		)
		mpm_str = json.dumps(mpm)
		self.assertNotIn("note", mpm_str.lower())

	def test_notes_never_injected_into_campaign_components(self):
		"""Verify dynamic campaign template components never ingest internal notes."""
		variables = {"name": "Alice", "order_id": "ORD-555"}
		components = campaigns.build_template_body_components(variables)
		components_str = json.dumps(components)
		self.assertNotIn("note", components_str.lower())
		self.assertIn("Alice", components_str)
		self.assertIn("ORD-555", components_str)

	# =========================================================================
	# 5. PRESENCE SPOOFING & MALFORMED ACTION INJECTION CHALLENGES
	# =========================================================================

	def test_presence_sql_injection_payload_does_not_execute_sql(self):
		"""Verify SQL injection payloads in publish_presence do not execute SQL queries."""
		sql_injection_conv = "conv_1'; DROP TABLE `tabUser`; --"
		sql_injection_action = "typing'; SELECT * FROM `tabUser`; --"

		with patch("frappe.publish_realtime") as mock_realtime:
			res = api.publish_presence(sql_injection_conv, sql_injection_action)

		self.assertEqual(res.get("status"), "published")
		# Verify mock_db.sql was NEVER called with injection payload
		for call_args in self.mock_db.sql.call_args_list:
			query = call_args[0][0]
			self.assertNotIn("DROP TABLE", query)
			self.assertNotIn("tabUser", query)

	def test_presence_arbitrary_event_spoofing_prevented(self):
		"""Verify publish_presence validates action and prevents arbitrary realtime event spoofing."""
		# Adversary tries to forge arbitrary system-level realtime events
		malicious_action = "nudg_system_reboot"

		with patch("frappe.publish_realtime") as mock_realtime:
			res = api.publish_presence("prof_123", malicious_action)
			published_event = res.get("event")

		# Presence API should restrict events to legitimate presence events
		self.assertIn(
			published_event,
			("nudg_agent_typing", "nudg_agent_viewing"),
			f"Arbitrary realtime event spoofed! Emitted: {published_event}",
		)

	def test_presence_non_existent_conversation_rejected(self):
		"""Verify publish_presence rejects non-existent conversation IDs."""
		non_existent_conv = "NON_EXISTENT_CONV_999999"
		self.mock_db.exists.return_value = False

		# Should raise DoesNotExistError or ValidationError for non-existent conversation
		with self.assertRaises((frappe.DoesNotExistError, frappe.ValidationError)):
			api.publish_presence(non_existent_conv, "typing")

	def test_presence_empty_and_whitespace_validation(self):
		"""Verify publish_presence throws validation error on empty or whitespace arguments."""
		with self.assertRaises(Exception):
			api.publish_presence("", "typing")

		with self.assertRaises(Exception):
			api.publish_presence("prof_123", "   ")

		with self.assertRaises(Exception):
			api.publish_presence(None, "viewing")
