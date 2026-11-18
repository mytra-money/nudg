# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import frappe

from nudg.services import analytics


class TestAnalyticsScope(unittest.TestCase):
	def setUp(self):
		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="agent@example.com")
		self.db = MagicMock()
		self.db.exists.return_value = True
		self.db.has_column.return_value = True
		self.db.count.return_value = 14
		frappe.local.db = self.db
		self.dates = patch.multiple(
			"nudg.services.analytics",
			today=lambda: "2026-11-18",
			getdate=lambda value=None: date(2026, 11, 18),
		)
		self.dates.start()
		self.addCleanup(self.dates.stop)

	def test_no_linked_account_does_not_count_site_messages(self):
		with patch("nudg.security.get_user_wa_accounts", return_value=[]):
			row = analytics._compute(None)

		self.db.count.assert_not_called()
		self.assertFalse(row["has_accounts"])
		self.assertEqual(row["messages_in"], 0)
		self.assertEqual(row["messages_out"], 0)
		self.assertEqual(row["open_conversations"], 0)

	def test_all_accounts_counts_only_permitted_accounts(self):
		with patch("nudg.security.get_user_wa_accounts", return_value=["ACC-1", "ACC-2"]):
			row = analytics._compute(None)

		self.assertTrue(row["has_accounts"])
		self.assertEqual(row["messages_in"], 14)
		for call in self.db.count.call_args_list:
			filters = call.args[1]
			self.assertEqual(filters["whatsapp_account"], ["in", ["ACC-1", "ACC-2"]])

	def test_other_users_account_is_rejected(self):
		def _deny(message, exc=Exception):
			raise exc(message)

		with patch("nudg.security.get_user_wa_accounts", return_value=["ACC-1"]):
			with patch("nudg.services.analytics._", side_effect=lambda message: message):
				with patch("nudg.services.analytics.frappe.throw", side_effect=_deny):
					with self.assertRaises(frappe.PermissionError):
						analytics._compute("ACC-SECRET")
		self.db.count.assert_not_called()
