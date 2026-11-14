# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

"""Hermetic unit tests for Interactive Commerce (SPM/MPM) & Inbound Cart Webhooks."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import frappe


class TestCommerceParity(unittest.TestCase):
	"""Test suite for SPM, MPM interactive message construction and inbound order parsing."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db"):
			self._saved[name] = getattr(frappe.local, name, None) if hasattr(frappe, "local") else None
		self._saved_cache = getattr(frappe, "cache", None)

		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="Administrator", data=frappe._dict())
		frappe.local.db = MagicMock()

		self.mock_cache = MagicMock()
		self.mock_cache.get_value.return_value = 0
		self.mock_cache.hget.return_value = {}
		frappe.cache = MagicMock(return_value=self.mock_cache)
		frappe.cache.hget.return_value = {}

	def tearDown(self):
		frappe.cache = self._saved_cache
		for name in ("flags", "session", "db"):
			val = self._saved.get(name)
			if val is not None:
				setattr(frappe.local, name, val)
		super().tearDown()

	# -------------------------------------------------------------------------
	# 1. Single-Product Message (SPM) Tests
	# -------------------------------------------------------------------------

	def test_build_spm_payload_success(self):
		from nudg.services.catalog import build_spm_payload

		payload = build_spm_payload(
			catalog_id="9876543210",
			product_retailer_id="SKU_BLUE_SHIRT",
			body_text="Check out our latest organic cotton shirt!",
			footer_text="Fast 2-day delivery available",
		)

		self.assertEqual(payload["type"], "product")
		self.assertEqual(payload["action"]["catalog_id"], "9876543210")
		self.assertEqual(payload["action"]["product_retailer_id"], "SKU_BLUE_SHIRT")
		self.assertEqual(payload["body"]["text"], "Check out our latest organic cotton shirt!")
		self.assertEqual(payload["footer"]["text"], "Fast 2-day delivery available")

	def test_build_spm_payload_missing_required_throws(self):
		from nudg.services.catalog import build_spm_payload

		with self.assertRaises(frappe.ValidationError):
			build_spm_payload(catalog_id="", product_retailer_id="SKU_1")

		with self.assertRaises(frappe.ValidationError):
			build_spm_payload(catalog_id="12345", product_retailer_id="")

	# -------------------------------------------------------------------------
	# 2. Multi-Product Message (MPM) Tests
	# -------------------------------------------------------------------------

	def test_build_mpm_payload_success(self):
		from nudg.services.catalog import build_mpm_payload

		sections = [
			{
				"title": "Smartphones",
				"product_items": [
					{"product_retailer_id": "PHONE_PRO_128"},
					{"product_retailer_id": "PHONE_MAX_256"},
				],
			},
			{
				"title": "Accessories",
				"product_retailer_ids": ["CASE_CLEAR_01", "CHARGER_65W"],
			},
		]

		payload = build_mpm_payload(
			catalog_id="CAT_998877",
			sections=sections,
			body_text="Explore our featured electronics",
			header_text="Autumn Sale",
			footer_text="Terms & Conditions apply",
		)

		self.assertEqual(payload["type"], "product_list")
		self.assertEqual(payload["header"]["text"], "Autumn Sale")
		self.assertEqual(payload["body"]["text"], "Explore our featured electronics")
		self.assertEqual(payload["footer"]["text"], "Terms & Conditions apply")
		self.assertEqual(payload["action"]["catalog_id"], "CAT_998877")

		formatted_sections = payload["action"]["sections"]
		self.assertEqual(len(formatted_sections), 2)
		self.assertEqual(formatted_sections[0]["title"], "Smartphones")
		self.assertEqual(len(formatted_sections[0]["product_items"]), 2)
		self.assertEqual(formatted_sections[1]["title"], "Accessories")
		self.assertEqual(len(formatted_sections[1]["product_items"]), 2)

	def test_build_mpm_payload_max_items_limit(self):
		"""Meta enforces a hard limit of 30 products across all sections in an MPM."""
		from nudg.services.catalog import build_mpm_payload

		huge_section = [
			{
				"title": "Bulk Items",
				"product_retailer_ids": [f"SKU_{i}" for i in range(35)],
			}
		]

		with self.assertRaises(frappe.ValidationError) as ctx:
			build_mpm_payload(catalog_id="CAT_01", sections=huge_section, body_text="Test")
		self.assertIn("30 products", str(ctx.exception))

	def test_build_mpm_payload_max_sections_limit(self):
		"""Meta enforces a limit of 10 sections per MPM."""
		from nudg.services.catalog import build_mpm_payload

		eleven_sections = [{"title": f"Sec {i}", "product_retailer_ids": ["SKU_1"]} for i in range(11)]
		with self.assertRaises(frappe.ValidationError) as ctx:
			build_mpm_payload(catalog_id="CAT_01", sections=eleven_sections, body_text="Test")
		self.assertIn("10 sections", str(ctx.exception))

	# -------------------------------------------------------------------------
	# 3. Inbound Cart / Order Webhook Parsing Tests
	# -------------------------------------------------------------------------

	def test_parse_inbound_order_payload(self):
		from nudg.services.catalog import parse_inbound_order

		order_data = {
			"catalog_id": "CATALOG_9900",
			"text": "Please leave at front door",
			"product_items": [
				{
					"product_retailer_id": "SHIRT_COTTON_BLUE_M",
					"quantity": 2,
					"item_price": 45.0,
					"currency": "USD",
				},
				{
					"product_retailer_id": "PANTS_CHINO_GREY_32",
					"quantity": 1,
					"item_price": 80.0,
					"currency": "USD",
				},
			],
		}

		result = parse_inbound_order(order_data)

		self.assertEqual(result["catalog_id"], "CATALOG_9900")
		self.assertEqual(result["customer_text"], "Please leave at front door")
		self.assertEqual(result["item_count"], 2)
		self.assertEqual(result["currency"], "USD")
		# Total: (2 * 45) + (1 * 80) = 90 + 80 = 170.0
		self.assertEqual(result["total_price"], 170.0)

		# Verify formatted summary string contains key order elements
		summary = result["summary_text"]
		self.assertIn("🛒 Order Placed (2 items)", summary)
		self.assertIn("SHIRT_COTTON_BLUE_M × 2 @ USD 45.00 = USD 90.00", summary)
		self.assertIn("PANTS_CHINO_GREY_32 × 1 @ USD 80.00 = USD 80.00", summary)
		self.assertIn("Total: USD 170.00", summary)
		self.assertIn("Customer Note: Please leave at front door", summary)

	# -------------------------------------------------------------------------
	# 4. Outbound Sending Helpers Tests
	# -------------------------------------------------------------------------

	def test_send_single_product_delegates_to_connector(self):
		from nudg.services.catalog import send_single_product

		with patch("nudg.integrations.connector.factory.get_connector") as mock_get_conn:
			mock_conn = MagicMock()
			mock_get_conn.return_value = mock_conn
			mock_conn.send_interactive.return_value = {"success": True, "message_id": "wamid.123"}

			resp = send_single_product(
				channel={"name": "Test Channel"},
				to="+15551234567",
				catalog_id="CAT_1",
				product_retailer_id="SKU_ITEM_1",
				body_text="Great offer",
			)

			self.assertTrue(resp["success"])
			mock_conn.send_interactive.assert_called_once()
			call_args = mock_conn.send_interactive.call_args
			payload = call_args[1]["interactive_payload"]
			self.assertEqual(payload["type"], "product")
			self.assertEqual(payload["action"]["product_retailer_id"], "SKU_ITEM_1")


if __name__ == "__main__":
	unittest.main()
