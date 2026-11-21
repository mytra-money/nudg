# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import inspect
import unittest
from unittest.mock import MagicMock, patch

import frappe

from nudg.desk_api import update_team_member
from nudg.invitations import assign_invited_roles, prepare_nudg_invitation
from nudg.security import (
	get_default_account,
	mark_first_account_default,
	on_user_created,
	set_account_default,
)


class TestSignupRole(unittest.TestCase):
	def _user(self, name="owner@example.com"):
		doc = MagicMock()
		doc.name = name
		doc.email = name
		doc.roles = []
		return doc

	def test_signup_user_gets_whatsapp_manager(self):
		doc = self._user()
		with (
			patch("nudg.security._nudg_invitation_exists", return_value=False),
			patch("nudg.security._is_signup_user", return_value=True),
			patch("nudg.security.frappe.db.exists", return_value="WhatsApp Manager"),
			patch("nudg.desk_access.profile_name_for_roles", return_value=None),
		):
			on_user_created(doc)
		doc.append.assert_called_once_with("roles", {"role": "WhatsApp Manager"})
		doc.save.assert_called_once()

	def test_invited_user_keeps_the_invited_role(self):
		doc = self._user("agent@example.com")
		with patch("nudg.security._nudg_invitation_exists", return_value=True):
			on_user_created(doc)
		doc.append.assert_not_called()

	def test_later_user_is_left_alone(self):
		doc = self._user("second@example.com")
		with (
			patch("nudg.security._nudg_invitation_exists", return_value=False),
			patch("nudg.security._is_signup_user", return_value=False),
		):
			on_user_created(doc)
		doc.append.assert_not_called()


class TestAccountDefault(unittest.TestCase):
	def test_first_account_is_the_default(self):
		doc = frappe._dict(name="ACC-1", owner="owner@example.com", is_default=0)
		with (
			patch("nudg.security._account_default_supported", return_value=True),
			patch("nudg.security.frappe.db.exists", return_value=None),
			patch("nudg.security.frappe.db.set_value") as set_value,
			patch("nudg.security.clear_account_caches"),
		):
			mark_first_account_default(doc)
		set_value.assert_called_once_with("WA Account", "ACC-1", "is_default", 1, update_modified=False)

	def test_later_account_stays_optional(self):
		doc = frappe._dict(name="ACC-2", owner="owner@example.com", is_default=0)
		with (
			patch("nudg.security._account_default_supported", return_value=True),
			patch("nudg.security.frappe.db.exists", return_value="ACC-1"),
			patch("nudg.security.frappe.db.set_value") as set_value,
		):
			mark_first_account_default(doc)
		set_value.assert_not_called()

	def test_checking_default_clears_the_owners_other_number(self):
		with (
			patch("nudg.security._account_default_supported", return_value=True),
			patch("nudg.security.frappe.db.get_value", return_value="owner@example.com"),
			patch("nudg.security.frappe.get_all", return_value=["ACC-1"]),
			patch("nudg.security.frappe.db.set_value") as set_value,
			patch("nudg.security.clear_account_caches"),
		):
			set_account_default("ACC-2", 1)
		self.assertEqual(
			set_value.call_args_list[0].args,
			("WA Account", "ACC-1", "is_default", 0),
		)
		self.assertEqual(
			set_value.call_args_list[1].args,
			("WA Account", "ACC-2", "is_default", 1),
		)

	def test_default_comes_from_assigned_accounts(self):
		with (
			patch("nudg.security.get_assigned_wa_accounts", return_value=["ACC-1", "ACC-2"]),
			patch("nudg.security._marked_default", return_value="ACC-2"),
		):
			self.assertEqual(get_default_account("agent@example.com"), "ACC-2")


class TestCrmRoleAssignment(unittest.TestCase):
	def test_manager_invitation_also_grants_the_user_role(self):
		user = MagicMock()
		assign_invited_roles(user, frappe._dict(nudg_role="WhatsApp Manager", roles=[]))
		user.append_roles.assert_called_once_with("WhatsApp Manager", "WhatsApp User")

	def test_user_invitation_grants_only_that_role(self):
		user = MagicMock()
		assign_invited_roles(user, frappe._dict(nudg_role="WhatsApp User", roles=[]))
		user.append_roles.assert_called_once_with("WhatsApp User")

	def test_desk_form_stores_one_role_and_nudg_path(self):
		doc = frappe._dict(app_name="nudg", nudg_role="WhatsApp Manager", roles=[], redirect_to_path="")
		doc.set = lambda key, value: setattr(doc, key, value)
		doc.append = lambda key, row: doc.roles.append(frappe._dict(row))
		prepare_nudg_invitation(doc)
		self.assertEqual(doc.nudg_role, "WhatsApp Manager")
		self.assertEqual([row.role for row in doc.roles], ["WhatsApp Manager"])
		self.assertEqual(doc.redirect_to_path, "/nudg")


class TestInviteHasNoPassword(unittest.TestCase):
	def test_team_update_does_not_take_a_password(self):
		self.assertNotIn("new_password", inspect.signature(update_team_member).parameters)
		self.assertNotIn("password", inspect.signature(update_team_member).parameters)
