# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import patch

import frappe

from nudg.desk_access import (
	PROFILE_AGENT,
	PROFILE_MANAGER,
	is_saas_site,
	profile_name_for_roles,
	user_blocked_from_desk,
)


class TestDeskAccess(unittest.TestCase):
	def setUp(self):
		super().setUp()
		frappe.local.flags = frappe._dict(mute_messages=True, in_test=True)
		frappe.local.session = frappe._dict(user="manager@example.com")
		self._nudg_saas = frappe.conf.get("nudg_saas") if getattr(frappe, "conf", None) else None
		if getattr(frappe, "conf", None) is not None:
			frappe.conf.nudg_saas = None

	def tearDown(self):
		if getattr(frappe, "conf", None) is not None:
			frappe.conf.nudg_saas = self._nudg_saas
		super().tearDown()

	def test_saas_when_only_nudg_apps_are_installed(self):
		with patch("nudg.desk_access.frappe.get_installed_apps", return_value=["frappe", "whatsapp", "nudg"]):
			self.assertTrue(is_saas_site())

	def test_self_hosted_when_another_app_is_installed(self):
		with patch("nudg.desk_access.frappe.get_installed_apps", return_value=["frappe", "erpnext", "nudg"]):
			self.assertFalse(is_saas_site())
		with patch("nudg.desk_access.frappe.get_installed_apps", return_value=["frappe", "lms", "nudg"]):
			self.assertFalse(is_saas_site())

	def test_site_config_overrides_installed_apps(self):
		frappe.conf.nudg_saas = 0
		with patch("nudg.desk_access.frappe.get_installed_apps", return_value=["frappe", "nudg"]):
			self.assertFalse(is_saas_site())
		frappe.conf.nudg_saas = 1
		with patch("nudg.desk_access.frappe.get_installed_apps", return_value=["frappe", "erpnext"]):
			self.assertTrue(is_saas_site())

	def test_saas_blocks_manager_and_user(self):
		with patch("nudg.desk_access.is_saas_site", return_value=True):
			self.assertEqual(profile_name_for_roles(["WhatsApp Manager"]), PROFILE_AGENT)
			self.assertEqual(profile_name_for_roles(["WhatsApp User"]), PROFILE_AGENT)
			self.assertIsNone(profile_name_for_roles(["System Manager", "WhatsApp Manager"]))

	def test_self_hosted_manager_keeps_whatsapp_modules(self):
		with patch("nudg.desk_access.is_saas_site", return_value=False):
			self.assertEqual(profile_name_for_roles(["WhatsApp Manager"]), PROFILE_MANAGER)
			self.assertEqual(profile_name_for_roles(["WhatsApp User"]), PROFILE_AGENT)

	def test_saas_desk_block_skips_system_manager_and_administrator(self):
		with patch("nudg.desk_access.is_saas_site", return_value=True), patch(
			"nudg.desk_access.frappe.get_roles", return_value=["WhatsApp Manager"]
		):
			self.assertTrue(user_blocked_from_desk("manager@example.com"))
		with patch("nudg.desk_access.is_saas_site", return_value=True), patch(
			"nudg.desk_access.frappe.get_roles", return_value=["WhatsApp User"]
		):
			self.assertTrue(user_blocked_from_desk("agent@example.com"))
		with patch("nudg.desk_access.is_saas_site", return_value=True), patch(
			"nudg.desk_access.frappe.get_roles", return_value=["System Manager", "WhatsApp Manager"]
		):
			self.assertFalse(user_blocked_from_desk("admin@example.com"))
		with patch("nudg.desk_access.is_saas_site", return_value=True):
			self.assertFalse(user_blocked_from_desk("Administrator"))

	def test_self_hosted_manager_is_not_blocked(self):
		with patch("nudg.desk_access.is_saas_site", return_value=False), patch(
			"nudg.desk_access.frappe.get_roles", return_value=["WhatsApp Manager"]
		):
			self.assertFalse(user_blocked_from_desk("manager@example.com"))
