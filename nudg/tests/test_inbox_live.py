# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

from __future__ import annotations

import unittest
from unittest.mock import patch

from nudg import api


class TestInboxLivePublish(unittest.TestCase):
	@patch("nudg.api.frappe.publish_realtime")
	@patch("nudg.api.frappe.db.exists", return_value=True)
	@patch("nudg.api._visible_message", return_value={"name": "MSG-1", "direction": "Incoming"})
	@patch("nudg.api._conversation_card", return_value={"profile": {"name": "PROF-1"}})
	def test_publish_sends_one_card(self, _card, _message, _exists, publish):
		api.publish_inbox_change("PROF-1", "MSG-1", bump=True)
		publish.assert_called_once()
		args, kwargs = publish.call_args
		self.assertEqual(args[0], "nudg_inbox")
		self.assertEqual(args[1]["profile"], "PROF-1")
		self.assertTrue(args[1]["bump"])
		self.assertEqual(args[1]["message"]["name"], "MSG-1")
		self.assertTrue(kwargs["after_commit"])

	@patch("nudg.api.frappe.log_error")
	@patch("nudg.api.frappe.publish_realtime")
	@patch("nudg.api.frappe.db.exists", return_value=True)
	@patch("nudg.api._conversation_card", side_effect=RuntimeError("db down"))
	def test_publish_never_raises(self, _card, _exists, publish, _log):
		api.publish_inbox_change("PROF-1", "MSG-1", bump=True)
		publish.assert_not_called()


if __name__ == "__main__":
	unittest.main()
