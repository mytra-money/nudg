# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import MagicMock, patch
import frappe
from nudg.security import (
	get_user_wa_accounts,
	ensure_account_user_permission,
	has_tenant_permission,
	get_tenant_conversation_query,
	get_tenant_campaign_query,
	get_tenant_rule_query,
	get_tenant_quick_reply_query,
	get_tenant_catalog_query,
)


class TestTenantIsolation(unittest.TestCase):
	def setUp(self):
		super().setUp()
		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="agent_a@example.com")
		self.mock_db = MagicMock()
		frappe.local.db = self.mock_db

	def test_administrator_bypasses_tenant_isolation(self):
		"""Administrator always has access regardless of account permissions."""
		doc = frappe._dict({"doctype": "NUDG Conversation", "whatsapp_account": "ACC-SECRET"})
		with patch("nudg.security._get_roles", return_value=["System Manager"]):
			self.assertTrue(has_tenant_permission(doc, user="Administrator"))
			query = get_tenant_conversation_query(user="Administrator")
			self.assertEqual(query, "")

	def test_get_user_wa_accounts_fetches_user_permissions(self):
		"""get_user_wa_accounts retrieves WA Account values allowed for user."""
		with patch("frappe.get_all", return_value=["ACC-ALPHA", "ACC-BETA"]):
			accounts = get_user_wa_accounts("agent_a@example.com")
			self.assertEqual(accounts, ["ACC-ALPHA", "ACC-BETA"])

	def test_has_tenant_permission_permits_matching_account(self):
		"""Access is granted when user is authorized for the document's account."""
		doc = frappe._dict({"doctype": "NUDG Conversation", "whatsapp_account": "ACC-ALPHA"})
		with patch("nudg.security._get_roles", return_value=["WhatsApp User"]), \
		     patch("nudg.security.get_user_wa_accounts", return_value=["ACC-ALPHA"]):
			self.assertTrue(has_tenant_permission(doc, user="agent_a@example.com"))

	def test_has_tenant_permission_blocks_cross_tenant_access(self):
		"""Access is denied when user attempts to access another tenant's document."""
		doc = frappe._dict({"doctype": "NUDG Conversation", "whatsapp_account": "ACC-BETA"})
		with patch("nudg.security._get_roles", return_value=["WhatsApp User"]), \
		     patch("nudg.security.get_user_wa_accounts", return_value=["ACC-ALPHA"]):
			self.assertFalse(has_tenant_permission(doc, user="agent_a@example.com"))

	def test_has_tenant_permission_allows_unassigned_document(self):
		"""Documents without account restriction (global/unassigned) are accessible."""
		doc = frappe._dict({"doctype": "NUDG Conversation", "whatsapp_account": None})
		with patch("nudg.security._get_roles", return_value=["WhatsApp User"]), \
		     patch("nudg.security.get_user_wa_accounts", return_value=["ACC-ALPHA"]):
			self.assertTrue(has_tenant_permission(doc, user="agent_a@example.com"))

	def test_tenant_conversation_query_filters_by_allowed_accounts(self):
		"""Query builder produces SQL condition restricting to user accounts."""
		with patch("nudg.security._get_roles", return_value=["WhatsApp User"]), \
		     patch("nudg.security.get_user_wa_accounts", return_value=["ACC-ALPHA"]):
			self.mock_db.escape.side_effect = lambda v: f"'{v}'"
			cond = get_tenant_conversation_query(user="agent_a@example.com")
			self.assertIn("`tabNUDG Conversation`.whatsapp_account IN ('ACC-ALPHA')", cond)

	def test_tenant_campaign_query_allows_general_and_assigned(self):
		"""UTM Campaign query condition isolates by account while keeping standard campaigns viewable."""
		with patch("nudg.security._get_roles", return_value=["WhatsApp User"]), \
		     patch("nudg.security.get_user_wa_accounts", return_value=["ACC-ALPHA"]):
			self.mock_db.escape.side_effect = lambda v: f"'{v}'"
			cond = get_tenant_campaign_query(user="agent_a@example.com")
			self.assertIn("`tabUTM Campaign`.whatsapp_account IN ('ACC-ALPHA')", cond)
			self.assertIn("`tabUTM Campaign`.whatsapp_account IS NULL", cond)

	def test_ensure_account_user_permission_idempotent(self):
		"""ensure_account_user_permission inserts only when not already present."""
		self.mock_db.exists.return_value = True
		res = ensure_account_user_permission("ACC-ALPHA", "agent_a@example.com")
		self.assertTrue(res)


if __name__ == "__main__":
	unittest.main()
