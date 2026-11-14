# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

from __future__ import annotations

import datetime
import unittest
from unittest.mock import MagicMock, patch

import frappe
from nudg.services import campaigns


class TestCampaignParity(unittest.TestCase):
	"""Comprehensive unit and integration test suite for Campaign Parity & Analytics."""

	def setUp(self):
		super().setUp()
		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Administrator")
		self.mock_db = MagicMock()
		frappe.local.db = self.mock_db

	def test_build_template_body_components_array(self):
		"""Positional array JSON converts to Meta text parameter components."""
		raw = '["Alice", "ORD-101", "$50.00"]'
		comps = campaigns.build_template_body_components(raw)
		self.assertIsNotNone(comps)
		self.assertEqual(len(comps), 1)
		self.assertEqual(comps[0]["type"], "body")
		params = comps[0]["parameters"]
		self.assertEqual(len(params), 3)
		self.assertEqual(params[0], {"type": "text", "text": "Alice"})
		self.assertEqual(params[1], {"type": "text", "text": "ORD-101"})
		self.assertEqual(params[2], {"type": "text", "text": "$50.00"})

	def test_build_template_body_components_positional_dict(self):
		"""Dict with numeric keys or {{n}} converts into ordered parameters."""
		raw = '{"2": "ORD-101", "1": "Alice"}'
		comps = campaigns.build_template_body_components(raw)
		params = comps[0]["parameters"]
		self.assertEqual(params[0]["text"], "Alice")
		self.assertEqual(params[1]["text"], "ORD-101")

		raw_curlies = '{"{{2}}": "ORD-101", "{{1}}": "Alice"}'
		comps_curlies = campaigns.build_template_body_components(raw_curlies)
		params_curlies = comps_curlies[0]["parameters"]
		self.assertEqual(params_curlies[0]["text"], "Alice")
		self.assertEqual(params_curlies[1]["text"], "ORD-101")

	def test_build_template_body_components_named_dict(self):
		"""Dict with named parameters retains parameter_name."""
		raw = '{"customer_name": "Alice", "order_id": "ORD-101"}'
		comps = campaigns.build_template_body_components(raw)
		params = comps[0]["parameters"]
		self.assertEqual(params[0]["parameter_name"], "customer_name")
		self.assertEqual(params[0]["text"], "Alice")
		self.assertEqual(params[1]["parameter_name"], "order_id")
		self.assertEqual(params[1]["text"], "ORD-101")

	def test_check_recipient_consent_opted_out(self):
		"""Consent check returns False for opted-out contact."""
		self.mock_db.exists.return_value = True
		self.mock_db.get_value.return_value = "Opted-Out"
		allowed = campaigns.check_recipient_consent(profile="contact_opted_out")
		self.assertFalse(allowed)

	def test_check_recipient_consent_active(self):
		"""Consent check returns True for active subscribed contact."""
		self.mock_db.exists.return_value = True
		self.mock_db.get_value.return_value = "Opted-In"
		allowed = campaigns.check_recipient_consent(profile="contact_opted_in")
		self.assertTrue(allowed)

	def test_scheduled_campaign_runner_due_campaigns(self):
		"""check_and_run_scheduled_campaigns triggers only campaigns where scheduled_at <= now."""
		now = datetime.datetime(2026, 11, 8, 12, 0, 0)
		with patch("nudg.services.campaigns.now_datetime", return_value=now), \
		     patch.object(frappe, "get_all", return_value=["CAMP-DUE-1", "CAMP-DUE-2"]), \
		     patch("nudg.services.campaigns.enqueue_run") as mock_enqueue:
			executed = campaigns.check_and_run_scheduled_campaigns(now=False)
			self.assertEqual(executed, ["CAMP-DUE-1", "CAMP-DUE-2"])
			self.assertEqual(mock_enqueue.call_count, 2)

	def test_recalculate_campaign_funnel_counts(self):
		"""Funnel aggregation correctly tallies Sent, Delivered, Read, and Failed."""
		mock_counts = [{
			"sent_count": 10,
			"delivered_count": 8,
			"read_count": 5,
			"failed_count": 2,
		}]
		self.mock_db.sql.return_value = mock_counts
		with patch.object(self.mock_db, "has_column", return_value=True):
			res = campaigns.recalculate_campaign_funnel_counts("CAMP-TEST")
			self.assertEqual(res["sent_count"], 10)
			self.assertEqual(res["delivered_count"], 8)
			self.assertEqual(res["read_count"], 5)
			self.assertEqual(res["failed_count"], 2)
			self.mock_db.set_value.assert_called_once()

	def test_update_campaign_recipient_status_precedence(self):
		"""Status cannot regress from Read to Delivered or Sent."""
		mock_row = [{"name": "row-1", "parent": "CAMP-TEST", "status": "Read"}]
		self.mock_db.sql.return_value = mock_row
		updated = campaigns.update_campaign_recipient_status("wamid.123", "delivered")
		self.assertFalse(updated)
		self.mock_db.set_value.assert_not_called()

	@patch("nudg.services.campaigns.check_recipient_consent")
	@patch("nudg.services.campaigns.get_connector")
	@patch("nudg.integrations.whatsapp.adapter.send_template")
	def test_run_campaign_pre_send_suppression_and_interpolation(
		self, mock_adapter_send, mock_get_connector, mock_consent
	):
		"""Opted-out recipient is skipped with status 'Skipped: Opted Out' and active recipient is sent."""
		mock_consent.side_effect = lambda prof, phone: False if prof == "opted_out_user" else True
		mock_adapter_send.return_value = "MSG-001"
		mock_get_connector.return_value = None

		doc = frappe._dict({
			"name": "CAMP-TEST-1",
			"whatsapp_status": "Draft",
			"status": "Draft",
			"whatsapp_template": "promo_deal",
			"template": "promo_deal",
			"whatsapp_account": "WA-ACC-1",
			"whatsapp_sent_count": 0,
			"whatsapp_failed_count": 0,
			"whatsapp_delivered_count": 0,
			"whatsapp_read_count": 0,
			"whatsapp_last_error": None,
			"whatsapp_recipients": [
				frappe._dict({
					"name": "r1",
					"profile": "opted_out_user",
					"phone_number": "+1234567890",
					"status": "Pending",
					"variables_json": '["10%"]',
					"message": None,
					"error_message": None,
				}),
				frappe._dict({
					"name": "r2",
					"profile": "active_user",
					"phone_number": "+1987654321",
					"status": "Pending",
					"variables_json": '["20%"]',
					"message": None,
					"error_message": None,
				}),
			],
			"save": MagicMock(),
		})

		with patch("frappe.get_doc", return_value=doc), \
		     patch("frappe.has_permission", return_value=True), \
		     patch("nudg.services.campaigns.recalculate_campaign_funnel_counts"):
			res = campaigns.run_campaign("CAMP-TEST-1")

			self.assertEqual(doc.whatsapp_recipients[0].status, "Skipped: Opted Out")
			self.assertIn("opted out", doc.whatsapp_recipients[0].error_message)

			self.assertEqual(doc.whatsapp_recipients[1].status, "Sent")
			self.assertEqual(doc.whatsapp_recipients[1].message, "MSG-001")
			mock_adapter_send.assert_called_once()
			self.assertEqual(mock_adapter_send.call_args[1]["components"], [{"type": "body", "parameters": [{"type": "text", "text": "20%"}]}])


if __name__ == "__main__":
	unittest.main()
