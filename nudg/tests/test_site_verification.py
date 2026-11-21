# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Site checks and the client-site retry queue. These tests do not call a live site."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import frappe

from nudg.integrations.erpnext.client import ERPNextClientError
from nudg.integrations.erpnext.verify import missing_permissions, verify_remote_site
from nudg.integrations.site_sync import ATTEMPTS, call_with_retry, is_site_down
from nudg.integrations.site_store import RemoteStore


def _meta(doctype: str, *, create=1, write=1, submit=1, read=1) -> dict:
	return {
		"name": doctype,
		"is_submittable": 1 if doctype == "WA Message" else 0,
		"permissions": [
			{"role": "System Manager", "permlevel": 0, "read": read, "create": create, "write": write, "submit": submit}
		],
	}


class _Remote:
	def __init__(self, user="Ada", roles=None, metas=None, error=None):
		self.user = user
		self.roles = roles if roles is not None else ["System Manager", "All"]
		self.metas = metas if metas is not None else {name: _meta(name) for name, _needed in (
			("WA Account", ()),
			("WA Profile", ()),
			("WA Message", ()),
		)}
		self.error = error

	def get_logged_user(self):
		if self.error:
			raise self.error
		return self.user

	def get_resource(self, doctype, name):
		return None

	def call_method(self, method, payload=None):
		if method.endswith("get_current_user_roles"):
			return {"message": self.roles}
		doctype = (payload or {}).get("doctype")
		if doctype not in self.metas:
			raise ERPNextClientError(f"{doctype} not found", status_code=404)
		return {"docs": [self.metas[doctype]]}


class _DownClient:
	def __init__(self):
		self.calls = 0

	def get_resources(self, doctype, **kwargs):
		return []

	def insert_resource(self, doctype, doc):
		self.calls += 1
		raise ERPNextClientError("Could not reach the ERPNext site.", retryable=True)

	def call_method(self, method, payload=None):
		return {"message": "ok"}


class TestSiteVerification(unittest.TestCase):
	def test_ready_site_is_connected(self):
		result = verify_remote_site(_Remote())
		self.assertTrue(result["ok"])
		self.assertEqual(result["status"], "Connected")
		self.assertEqual(result["remote_user"], "Ada")
		self.assertFalse(result["reason"])

	def test_missing_doctype_is_explained(self):
		metas = {name: _meta(name) for name in ("WA Profile", "WA Message")}
		result = verify_remote_site(_Remote(metas=metas))
		self.assertFalse(result["ok"])
		self.assertEqual(result["status"], "Error")
		self.assertIn("WA Account is not installed", result["reason"])

	def test_missing_permission_is_explained(self):
		metas = {
			"WA Account": _meta("WA Account", create=0),
			"WA Profile": _meta("WA Profile"),
			"WA Message": _meta("WA Message"),
		}
		result = verify_remote_site(_Remote(metas=metas))
		self.assertFalse(result["ok"])
		self.assertIn("cannot create WA Account", result["reason"])

	def test_unreachable_site_is_an_error(self):
		result = verify_remote_site(
			_Remote(error=ERPNextClientError("Could not reach the ERPNext site.", retryable=True))
		)
		self.assertFalse(result["ok"])
		self.assertEqual(result["status"], "Error")
		self.assertIn("not reachable", result["reason"])

	def test_administrator_skips_role_permissions(self):
		self.assertEqual(missing_permissions(_meta("WA Account", create=0), {"Administrator"}, ("read", "create")), [])

	def test_push_is_tried_three_times(self):
		calls = {"n": 0}

		def fail():
			calls["n"] += 1
			raise ERPNextClientError("down", retryable=True)

		result, error = call_with_retry(fail)
		self.assertIsNone(result)
		self.assertEqual(calls["n"], ATTEMPTS)
		self.assertTrue(is_site_down(error))

	def test_down_client_keeps_the_message_after_three_tries(self):
		client = _DownClient()
		store = RemoteStore("WA-REMOTE", object(), client)
		frappe.local.flags = frappe._dict()
		frappe.local.db = MagicMock()
		frappe.db.get_value.return_value = None
		with patch("nudg.integrations.site_sync.mark_site_unreachable") as mark, \
			patch("nudg.integrations.site_sync.remember_message") as remember, \
			patch("nudg.integrations.site_store.frappe.log_error"), \
			patch("whatsapp.whatsapp.webhook._create_incoming_message", side_effect=RuntimeError("no local")):
			store._incoming(
				{"id": "wamid.IN1", "from": "15551230000", "type": "text", "text": {"body": "Hello"}},
				"Ada",
			)
		self.assertEqual(client.calls, ATTEMPTS)
		mark.assert_called()
		remember.assert_called()
		self.assertEqual(remember.call_args.args[4], "wamid.IN1")
		self.assertEqual(remember.call_args.kwargs["message"], "Hello")
		self.assertTrue(remember.call_args.kwargs["pending"])


class TestHeldReplay(unittest.TestCase):
	def test_replay_writes_a_held_message_once_the_site_answers(self):
		client = MagicMock()
		client.get_resources.return_value = []
		client.insert_resource.side_effect = lambda doctype, doc: {"name": f"{doctype}-1", **doc}
		store = RemoteStore("WA-REMOTE", object(), client)
		store.remote_account = MagicMock(return_value="REMOTE-ACC")
		store.ensure_profile = MagicMock(return_value="REMOTE-PROF")
		ok = store.push_message(
			{
				"phone": "+15551230000",
				"profile_name": "Ada",
				"direction": "Incoming",
				"message": "Hello",
				"message_id": "wamid.IN1",
				"status": "Sent",
			}
		)
		self.assertTrue(ok)
		inserted = client.insert_resource.call_args.args[1]
		self.assertEqual(inserted["message_id"], "wamid.IN1")
		self.assertEqual(inserted["to"], "REMOTE-PROF")
