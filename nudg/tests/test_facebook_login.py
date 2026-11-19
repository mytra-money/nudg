# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from nudg.integrations import facebook_login


class TestFacebookLogin(unittest.TestCase):
	def test_new_facebook_user_gets_whatsapp_user(self):
		self.assertEqual(facebook_login.role_to_grant(["facebook"], []), "WhatsApp User")

	def test_existing_roles_are_not_replaced(self):
		self.assertIsNone(facebook_login.role_to_grant(["facebook"], ["WhatsApp Manager"]))
		self.assertIsNone(facebook_login.role_to_grant(["facebook"], ["System Manager"]))
		self.assertIsNone(facebook_login.role_to_grant(["google"], []))

	def test_default_login_lands_in_nudg(self):
		self.assertEqual(facebook_login.nudg_landing("https://nudg.example/desk/workspace"), "/nudg")
		self.assertEqual(facebook_login.nudg_landing("/me"), "/nudg")
		self.assertIsNone(facebook_login.nudg_landing("/nudg"))
		self.assertIsNone(facebook_login.nudg_landing("/desk/user"))

	def test_settings_view_hides_the_secret(self):
		doc = SimpleNamespace(enable_social_login=1, client_id="752752485429112", client_secret="hidden")
		view = facebook_login.describe(doc, True, "https://nudg.example/callback")
		self.assertNotIn("client_secret", view)
		self.assertNotIn("hidden", view.values())
		self.assertTrue(view["ready"])
		self.assertEqual(view["provider"], "facebook")

	def test_apply_settings_requires_a_numeric_app_id(self):
		doc = SimpleNamespace(enable_social_login=0, client_id="", client_secret="", sign_ups="", api_endpoint="", api_endpoint_args="")
		with patch.object(facebook_login.frappe, "throw", side_effect=frappe.ValidationError("bad")):
			with self.assertRaises(frappe.ValidationError):
				facebook_login.apply_settings(doc, "not-a-number", "secret", True, False)

	def test_apply_settings_keeps_a_saved_secret(self):
		doc = SimpleNamespace(
			enable_social_login=0,
			client_id="",
			client_secret="keep",
			sign_ups="",
			api_endpoint="",
			api_endpoint_args="",
		)
		facebook_login.apply_settings(doc, "752752485429112", "", True, True)
		self.assertEqual(doc.client_id, "752752485429112")
		self.assertEqual(doc.client_secret, "keep")
		self.assertEqual(doc.enable_social_login, 1)
		self.assertEqual(doc.sign_ups, "Allow")
		self.assertEqual(doc.api_endpoint, facebook_login.API_ENDPOINT)

	def test_grant_skips_a_user_who_did_not_use_facebook(self):
		user = SimpleNamespace(name="agent@example.com", social_logins=[], roles=[], flags=frappe._dict(), added=[])

		def add_roles(*roles):
			user.added.extend(roles)

		user.add_roles = add_roles
		with patch.object(facebook_login.frappe, "db") as db:
			db.exists.return_value = True
			facebook_login.grant_new_facebook_user(user)
		self.assertEqual(user.added, [])

	def test_grant_adds_whatsapp_user_for_facebook_signup(self):
		user = SimpleNamespace(
			name="new@example.com",
			social_logins=[SimpleNamespace(provider="facebook")],
			roles=[],
			flags=frappe._dict(),
			added=[],
		)

		def add_roles(*roles):
			user.added.extend(roles)

		user.add_roles = add_roles
		with patch.object(facebook_login.frappe, "db") as db:
			db.exists.return_value = True
			facebook_login.grant_new_facebook_user(user)
		self.assertEqual(user.added, ["WhatsApp User"])

	def test_login_stays_closed_until_the_key_is_enabled(self):
		with patch.object(facebook_login, "_login_enabled", return_value=False), patch.object(
			facebook_login.frappe, "throw", side_effect=frappe.PermissionError("off")
		):
			with self.assertRaises(frappe.PermissionError):
				facebook_login.login_via_facebook("code", "state")

	def test_enabled_login_rewrites_the_desk_landing(self):
		def finish(code, state):
			frappe.local.response = {"location": "/desk/workspace"}

		with patch.object(facebook_login, "_login_enabled", return_value=True), patch(
			"frappe.integrations.oauth2_logins.login_via_facebook", side_effect=finish
		):
			facebook_login.login_via_facebook("code", "state")
		self.assertEqual(frappe.local.response["location"], "/nudg")
