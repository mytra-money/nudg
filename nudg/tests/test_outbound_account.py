# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

from __future__ import annotations

import unittest
from unittest.mock import patch

from nudg.services.outbound import bind_outgoing_account


class _Message:
	def __init__(self, **kwargs):
		self.__dict__.update(kwargs)

	def get(self, key, default=None):
		return getattr(self, key, default)

	def set(self, key, value):
		setattr(self, key, value)


class TestBindOutgoingAccount(unittest.TestCase):
	def _bind(self, doc, profile_account="WhatsApp 6909", phone_id="155512126909"):
		with (
			patch("nudg.services.outbound._profile_account", return_value=profile_account),
			patch("nudg.services.outbound._phone_id", return_value=phone_id) as phone,
		):
			bind_outgoing_account(doc)
			return phone

	def test_profile_account_replaces_site_default(self):
		doc = _Message(
			direction="Outgoing",
			docstatus=0,
			_action="save",
			to="nagarajukodela",
			whatsapp_account="WhatsApp 0564",
		)
		doc.set("from", "1286969637830564")

		self._bind(doc)

		self.assertEqual(doc.whatsapp_account, "WhatsApp 6909")
		self.assertEqual(doc.get("from"), "155512126909")

	def test_submit_of_saved_draft_still_rebinds(self):
		doc = _Message(
			direction="Outgoing",
			docstatus=1,
			_action="submit",
			to="nagarajukodela",
			whatsapp_account="WhatsApp 0564",
		)
		doc.set("from", "1286969637830564")

		self._bind(doc)

		self.assertEqual(doc.whatsapp_account, "WhatsApp 6909")
		self.assertEqual(doc.get("from"), "155512126909")

	def test_matching_account_is_left_alone(self):
		doc = _Message(
			direction="Outgoing",
			docstatus=0,
			_action="save",
			to="nagarajukodela",
			whatsapp_account="WhatsApp 6909",
		)
		doc.set("from", "155512126909")

		self._bind(doc)

		self.assertEqual(doc.whatsapp_account, "WhatsApp 6909")
		self.assertEqual(doc.get("from"), "155512126909")

	def test_profile_without_account_keeps_current_sender(self):
		doc = _Message(
			direction="Outgoing",
			docstatus=0,
			_action="save",
			to="nagarajukodela",
			whatsapp_account="WhatsApp 0564",
		)
		doc.set("from", "1286969637830564")

		self._bind(doc, profile_account=None)

		self.assertEqual(doc.whatsapp_account, "WhatsApp 0564")
		self.assertEqual(doc.get("from"), "1286969637830564")

	def test_incoming_is_ignored(self):
		doc = _Message(direction="Incoming", docstatus=0, to="nagarajukodela", whatsapp_account="WhatsApp 0564")
		with patch("nudg.services.outbound._profile_account") as profile:
			bind_outgoing_account(doc)
		self.assertEqual(doc.whatsapp_account, "WhatsApp 0564")
		profile.assert_not_called()

	def test_submitted_update_is_ignored(self):
		doc = _Message(
			direction="Outgoing",
			docstatus=1,
			_action="update_after_submit",
			to="nagarajukodela",
			whatsapp_account="WhatsApp 0564",
		)
		with patch("nudg.services.outbound._profile_account") as profile:
			bind_outgoing_account(doc)
		self.assertEqual(doc.whatsapp_account, "WhatsApp 0564")
		profile.assert_not_called()


if __name__ == "__main__":
	unittest.main()
