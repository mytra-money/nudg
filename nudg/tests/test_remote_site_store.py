# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Connected sites store WA Message remotely. Local accounts stay on this database."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import frappe

from nudg.integrations import site_store, webhook


class _Client:
	def __init__(self):
		self.inserted = []
		self.calls = []
		self.resources = []

	def get_resources(self, doctype, **kwargs):
		return [row for row in self.resources if row.get("doctype", doctype) == doctype]

	def insert_resource(self, doctype, doc):
		saved = {"name": f"{doctype}-{len(self.inserted) + 1}", **doc}
		self.inserted.append((doctype, doc))
		return saved

	def call_method(self, method, payload=None):
		self.calls.append((method, payload))
		return {"message": "ok"}


class TestRemoteSiteStore(unittest.TestCase):
	def setUp(self):
		self._saved = {}
		for name in ("flags", "db"):
			self._saved[name] = getattr(frappe.local, name, None)
		frappe.local.flags = frappe._dict()
		frappe.local.db = MagicMock()
		frappe.local.response = frappe._dict()
		frappe.db.exists.return_value = True
		frappe.db.has_column.return_value = True
		frappe.db.get_value.return_value = None

	def tearDown(self):
		for name, value in self._saved.items():
			if value is not None:
				setattr(frappe.local, name, value)

	def test_local_account_is_not_remote(self):
		frappe.db.get_value.return_value = "Pending"
		self.assertFalse(site_store.stores_remotely("WA-LOCAL"))
		self.assertFalse(site_store.payload_is_remote({"entry": []}))

	def test_incoming_is_written_to_the_connected_site(self):
		client = _Client()
		store = site_store.RemoteStore("WA-REMOTE", object(), client)
		frappe.db.get_value.side_effect = lambda *args, **kwargs: {
			("WA Account", "WA-REMOTE", "phone_id"): "100200",
			("WA Account", "WA-REMOTE", "account_name"): "Support",
		}.get(args[:3] if len(args) >= 3 else args)

		with patch("nudg.integrations.whatsapp.adapter.ensure_local_profile", return_value="PROF-1"), \
			patch("nudg.services.consent.handle_incoming_consent", return_value=(False, None)), \
			patch("nudg.chatbot.processor.ChatbotProcessor") as processor, \
			patch("nudg.api.publish_inbox_change") as publish:
			store.take({
				"contacts": [{"profile": {"name": "Ada"}}],
				"messages": [{
					"id": "wamid.IN1",
					"from": "15551230000",
					"type": "text",
					"text": {"body": "Hello"},
					"timestamp": "1700000000",
				}],
			})

		doctypes = [doctype for doctype, _doc in client.inserted]
		self.assertEqual(doctypes, ["WA Account", "WA Profile", "WA Message"])
		message = next(doc for doctype, doc in client.inserted if doctype == "WA Message")
		self.assertEqual(message["direction"], "Incoming")
		self.assertEqual(message["message_id"], "wamid.IN1")
		self.assertEqual(message["message"], "Hello")
		self.assertEqual(client.calls[0][0], "frappe.client.submit")
		processor.assert_called_once()
		publish.assert_called_once()
		self.assertEqual(publish.call_args.kwargs["message"]["to"], "PROF-1")
		self.assertIn("Hello", message["message"])

	def test_duplicate_incoming_is_not_stored_again(self):
		client = _Client()
		client.resources = [{"doctype": "WA Message", "name": "MSG-1", "message_id": "wamid.IN1", "status": "Sent"}]
		store = site_store.RemoteStore("WA-REMOTE", object(), client)
		store._incoming({"id": "wamid.IN1", "from": "1555", "type": "text", "text": {"body": "Again"}}, "Ada")
		self.assertEqual(client.inserted, [])

	def test_outgoing_is_sent_here_and_stored_there(self):
		client = _Client()
		store = site_store.RemoteStore("WA-REMOTE", object(), client)
		with patch.object(store, "ensure_profile", return_value="REMOTE-PROF"), \
			patch.object(store, "remote_account", return_value="REMOTE-ACC"), \
			patch.object(site_store, "connected_site", return_value=object()), \
			patch.object(site_store.RemoteStore, "for_account", return_value=store), \
			patch("nudg.integrations.whatsapp.adapter.deliver_text", return_value="wamid.OUT1") as deliver:
			name = site_store.send_text("+15551230000", "WA-REMOTE", "Reply")

		deliver.assert_called_once()
		self.assertEqual(name, "WA Message-1")
		message = next(doc for doctype, doc in client.inserted if doctype == "WA Message")
		self.assertEqual(message["direction"], "Outgoing")
		self.assertEqual(message["status"], "Sent")
		self.assertEqual(message["message_id"], "wamid.OUT1")
		self.assertEqual(message["to"], "REMOTE-PROF")
		self.assertFalse(any(call[0] == "frappe.client.submit" for call in client.calls))

	def test_webhook_uses_the_remote_store(self):
		payload = {"entry": [{"changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": "100200"}}}]}]}
		with patch.object(site_store, "payload_is_remote", return_value=True), \
			patch.object(webhook, "_verify_meta_signature") as verify, \
			patch.object(site_store, "ingest") as ingest, \
			patch("whatsapp.whatsapp.webhook.handler") as official:
			frappe.local.request = MagicMock()
			frappe.local.request.method = "POST"
			frappe.local.request.get_data.return_value = b"{}"
			frappe.flags.nudg_webhook_payload = None
			with patch.object(webhook, "_peek_payload", return_value=payload):
				result = webhook.handler()

		self.assertEqual(result, "ok")
		verify.assert_called_once()
		ingest.assert_called_once_with(payload)
		official.assert_not_called()
