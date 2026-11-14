# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

from __future__ import annotations

import datetime
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import now_datetime

from nudg import api, desk_api
from nudg.services import assignments


class TestInboxAndPresenceParity(unittest.TestCase):
	"""Hermetic unit tests for Notes, Tags, Presence, and Round-Robin routing."""

	def setUp(self):
		super().setUp()
		self._saved = {}
		for name in ("flags", "session", "db", "site", "cache"):
			self._saved[name] = getattr(frappe.local, name, None) if name != "cache" else getattr(frappe, "cache", None)

		self._saved_client_cache = getattr(frappe, "client_cache", None)
		self.mock_client_cache = MagicMock()
		frappe.client_cache = self.mock_client_cache

		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="test_agent@example.com", data=frappe._dict())
		frappe.local.site = "test.local"
		self.mock_db = MagicMock()
		frappe.local.db = self.mock_db

		self.mock_cache = MagicMock()
		self.mock_cache.get_value.return_value = 0
		frappe.cache = MagicMock(return_value=self.mock_cache)

	def tearDown(self):
		frappe.cache = self._saved.get("cache")
		frappe.client_cache = self._saved_client_cache
		for name in ("flags", "session", "db", "site"):
			val = self._saved.get(name)
			if val is not None:
				setattr(frappe.local, name, val)
			else:
				try:
					delattr(frappe.local, name)
				except AttributeError:
					pass
		super().tearDown()

	# -------------------------------------------------------------------------
	# 1. Internal Notes Tests
	# -------------------------------------------------------------------------

	def test_note_doctype_schema_structure(self):
		"""Assert NUDG Conversation schema contains required fields."""
		app_path = Path(frappe.get_app_path("nudg"))
		schema_file = app_path / "nudg" / "doctype" / "nudg_conversation" / "nudg_conversation.json"
		self.assertTrue(schema_file.exists(), f"Schema missing: {schema_file}")

		data = json.loads(schema_file.read_text())
		self.assertEqual(data.get("doctype"), "DocType")
		self.assertEqual(data.get("name"), "NUDG Conversation")

		fields = {f["fieldname"]: f for f in data.get("fields", [])}
		self.assertIn("profile", fields)
		self.assertIn("assignment_status", fields)
		self.assertIn("whatsapp_account", fields)

	# -------------------------------------------------------------------------
	# 2. Conversation Tags Tests
	# -------------------------------------------------------------------------

	def test_tag_normalization(self):
		"""Verify string, list, and JSON inputs are normalized properly."""
		str_val, list_val = assignments._normalize_tags("VIP, Billing, Urgent")
		self.assertEqual(str_val, "VIP, Billing, Urgent")
		self.assertEqual(list_val, ["VIP", "Billing", "Urgent"])

		str_val2, list_val2 = assignments._normalize_tags(["High Priority", "Escalated"])
		self.assertEqual(str_val2, "High Priority, Escalated")
		self.assertEqual(list_val2, ["High Priority", "Escalated"])

		str_val3, list_val3 = assignments._normalize_tags('["Tier1", "Sales"]')
		self.assertEqual(str_val3, "Tier1, Sales")
		self.assertEqual(list_val3, ["Tier1", "Sales"])

	@patch("frappe.publish_realtime")
	@patch("nudg.services.assignments.ensure_conversation", return_value="CONV-001")
	@patch("frappe.has_permission", return_value=True)
	def test_set_conversation_tags(self, mock_perm, mock_ensure, mock_publish):
		"""Verify setting tags updates conversation and publishes event."""
		mock_conv = MagicMock()
		mock_conv.name = "CONV-001"
		mock_conv.profile = "profile_1"
		mock_conv.tags = ""
		mock_conv.assignment_status = "Unassigned"
		mock_conv.assignee = None
		mock_conv.priority = "Medium"
		mock_conv.last_assigned_on = None
		mock_conv.assignment_source = "Manual"
		mock_conv.whatsapp_account = "WA-ACC-1"

		with patch("frappe.get_doc", return_value=mock_conv):
			res = desk_api.set_conversation_tags("profile_1", ["VIP", "Urgent"])
			self.assertEqual(mock_conv.tags, "VIP, Urgent")
			self.assertEqual(res["tags"], ["VIP", "Urgent"])
			mock_publish.assert_called_once()
			self.assertEqual(mock_publish.call_args[0][0], "nudg_conversation_tags_updated")

	# -------------------------------------------------------------------------
	# 3. Collision Detection & Live Presence Tests
	# -------------------------------------------------------------------------

	def test_publish_presence_guest_denied(self):
		"""Guest cannot publish presence."""
		frappe.local.session.user = "Guest"
		with self.assertRaises(frappe.PermissionError):
			api.publish_presence("CONV-001", "viewing")

	@patch("frappe.publish_realtime")
	def test_publish_presence_viewing(self, mock_publish):
		"""Verify viewing action broadcasts nudg_agent_viewing."""
		res = api.publish_presence("CONV-001", "viewing")
		self.assertEqual(res["status"], "published")
		self.assertEqual(res["event"], "nudg_agent_viewing")
		mock_publish.assert_called_once()
		self.assertEqual(mock_publish.call_args[1]["event"], "nudg_agent_viewing")
		self.assertEqual(mock_publish.call_args[1]["message"]["conversation_id"], "CONV-001")
		self.assertTrue(mock_publish.call_args[1]["message"]["active"])

	@patch("frappe.publish_realtime")
	def test_publish_presence_typing(self, mock_publish):
		"""Verify typing action broadcasts nudg_agent_typing."""
		res = api.publish_presence("CONV-001", "typing")
		self.assertEqual(res["event"], "nudg_agent_typing")
		self.assertTrue(res["payload"]["active"])

		# Stopped typing
		res_stop = api.publish_presence("CONV-001", "stopped_typing")
		self.assertEqual(res_stop["event"], "nudg_agent_typing")
		self.assertFalse(res_stop["payload"]["active"])

	# -------------------------------------------------------------------------
	# 4. Round-Robin Auto-Routing Tests
	# -------------------------------------------------------------------------

	@patch("nudg.services.assignments.get_eligible_desk_agents")
	def test_auto_assign_round_robin_fair_distribution(self, mock_agents):
		"""Test round-robin routes across agents sequentially."""
		mock_agents.return_value = ["agent_a@example.com", "agent_b@example.com", "agent_c@example.com"]

		with patch("nudg.services.assignments.ensure_conversation") as mock_ensure, \
			 patch("frappe.publish_realtime"), \
			 patch("nudg.services.assignments._sync_todo"):

			conv_docs = []
			for i in range(4):
				c = MagicMock()
				c.name = f"CONV-{i+1}"
				c.profile = f"profile_{i+1}"
				c.assignee = None
				c.assignment_status = "Unassigned"
				c.assignment_source = "Manual"
				c.last_assigned_on = None
				conv_docs.append(c)

			# 1st assignment -> agent_a
			with patch("frappe.get_doc", return_value=conv_docs[0]), \
				 patch("frappe.get_all", return_value=[]):
				res1 = assignments.auto_assign_round_robin(conv_docs[0])
				self.assertEqual(res1["assignee"], "agent_a@example.com")
				self.assertEqual(conv_docs[0].assignment_source, "Round Robin")

			# 2nd assignment -> agent_b
			with patch("frappe.get_doc", return_value=conv_docs[1]), \
				 patch("frappe.get_all", return_value=[frappe._dict({"assignee": "agent_a@example.com", "last_assigned_on": datetime.datetime(2026, 11, 8, 11, 0, 0)})]):
				res2 = assignments.auto_assign_round_robin(conv_docs[1])
				self.assertEqual(res2["assignee"], "agent_b@example.com")

			# 3rd assignment -> agent_c
			with patch("frappe.get_doc", return_value=conv_docs[2]), \
				 patch("frappe.get_all", return_value=[
					 frappe._dict({"assignee": "agent_b@example.com", "last_assigned_on": datetime.datetime(2026, 11, 8, 11, 30, 0)}),
					 frappe._dict({"assignee": "agent_a@example.com", "last_assigned_on": datetime.datetime(2026, 11, 8, 11, 0, 0)})
				 ]):
				res3 = assignments.auto_assign_round_robin(conv_docs[2])
				self.assertEqual(res3["assignee"], "agent_c@example.com")

	@patch("nudg.services.assignments.get_eligible_desk_agents")
	def test_auto_assign_skips_already_assigned(self, mock_agents):
		"""Already assigned conversations are not modified."""
		mock_agents.return_value = ["agent_a@example.com", "agent_b@example.com"]
		c = MagicMock()
		c.name = "CONV-LOCKED"
		c.profile = "profile_locked"
		c.assignee = "agent_assigned@example.com"
		c.assignment_status = "Assigned"
		c.assignment_source = "Manual"
		c.last_assigned_on = datetime.datetime(2026, 11, 8, 12, 0, 0)

		res = assignments.auto_assign_round_robin(c)
		self.assertEqual(res["assignee"], "agent_assigned@example.com")
		c.save.assert_not_called()

	@patch("frappe.has_permission", return_value=True)
	@patch("nudg.api._ready", return_value=True)
	@patch("frappe.get_list")
	def test_get_inbox_tag_filtering(self, mock_get_list, mock_ready, mock_perm):
		"""Verify get_inbox filters conversations by tag."""
		profiles = [
			frappe._dict({"name": "prof_vip", "whatsapp_account": "WA-1", "phone_number": "+111"}),
			frappe._dict({"name": "prof_regular", "whatsapp_account": "WA-1", "phone_number": "+222"}),
		]
		mock_get_list.side_effect = lambda dt, **kwargs: profiles if dt == "WA Profile" else []

		with patch("nudg.services.assignments.get_conversation_map") as mock_map, \
		     patch("nudg.services.assignments.ensure_conversation"):
			mock_map.return_value = {
				"prof_vip": {"name": "c1", "tags": "VIP, Priority", "assignment_status": "Unassigned"},
				"prof_regular": {"name": "c2", "tags": "Support", "assignment_status": "Unassigned"},
			}
			res = api.get_inbox(tag="VIP")
			convs = res["conversations"]
			self.assertEqual(len(convs), 1)
			self.assertEqual(convs[0]["profile"]["name"], "prof_vip")


if __name__ == "__main__":
	unittest.main()
