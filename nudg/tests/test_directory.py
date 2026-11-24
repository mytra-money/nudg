# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import MagicMock, patch

import frappe

from nudg.services import directory


def _throw(message, exc=None):
	raise (exc or frappe.ValidationError)(str(message))


class TestDirectoryPermissions(unittest.TestCase):
	def test_access_reads_role_permissions(self):
		def allowed(doctype, ptype, **kwargs):
			if doctype == "WA Profile":
				return ptype in ("read", "write", "create")
			if doctype == "WA Recipient List":
				return ptype == "read"
			return False

		with (
			patch("nudg.services.directory._doctype_exists", return_value=True),
			patch("nudg.services.directory.frappe.has_permission", side_effect=allowed),
		):
			flags = directory.access()

		self.assertTrue(flags["profile"]["create"])
		self.assertFalse(flags["profile"]["delete"])
		self.assertTrue(flags["recipient_list"]["read"])
		self.assertFalse(flags["recipient_list"]["write"])
		self.assertFalse(flags["recipient_list"]["create"])

	def test_new_profile_is_refused_without_create_permission(self):
		def allowed(doctype, ptype, doc=None, throw=False):
			ok = ptype == "read"
			if throw and not ok:
				_throw("no", frappe.PermissionError)
			return ok

		with (
			patch("nudg.services.directory._doctype_exists", return_value=True),
			patch("nudg.services.directory._assert_account", return_value="ACC-1"),
			patch("nudg.services.directory.profile_phone", return_value="+919800000000"),
			patch("nudg.utils.phone.find_matching_profile", return_value=None),
			patch("nudg.services.directory.frappe.has_permission", side_effect=allowed),
			patch("nudg.services.directory.frappe.new_doc") as new_doc,
			patch("nudg.services.directory.frappe.throw", side_effect=_throw),
		):
			with self.assertRaises(frappe.PermissionError):
				directory.save_profile(
					profile_name="Asha",
					phone_number="+919800000000",
					whatsapp_account="ACC-1",
				)
		new_doc.assert_not_called()

	def test_new_profile_inserts_when_create_is_allowed(self):
		doc = MagicMock()
		doc.name = "PROF-1"
		doc.profile_name = "Asha"
		doc.phone_number = "+919800000000"
		doc.whatsapp_account = "ACC-1"
		doc.status = "Active"

		with (
			patch("nudg.services.directory._doctype_exists", return_value=True),
			patch("nudg.services.directory._assert_account", return_value="ACC-1"),
			patch("nudg.services.directory.profile_phone", return_value="+919800000000"),
			patch("nudg.utils.phone.find_matching_profile", return_value=None),
			patch("nudg.services.directory.frappe.has_permission", return_value=True),
			patch("nudg.services.directory.frappe.new_doc", return_value=doc),
		):
			saved = directory.save_profile(
				profile_name="Asha",
				phone_number="9800000000",
				whatsapp_account="ACC-1",
			)

		doc.insert.assert_called_once_with()
		self.assertEqual(saved["name"], "PROF-1")
		self.assertTrue(saved["created"])

	def test_existing_number_opens_the_profile_without_a_second_insert(self):
		doc = MagicMock()
		doc.name = "PROF-9"
		doc.profile_name = "Asha"
		doc.phone_number = "+919800000000"
		doc.whatsapp_account = "ACC-1"
		doc.status = "Active"

		def allowed(doctype, ptype, doc=None, throw=False):
			return ptype == "read"

		with (
			patch("nudg.services.directory._doctype_exists", return_value=True),
			patch("nudg.services.directory._assert_account", return_value="ACC-1"),
			patch("nudg.services.directory.profile_phone", return_value="+919800000000"),
			patch("nudg.utils.phone.find_matching_profile", return_value="PROF-9"),
			patch("nudg.services.directory.frappe.has_permission", side_effect=allowed),
			patch("nudg.services.directory.frappe.get_doc", return_value=doc),
			patch("nudg.services.directory.frappe.new_doc") as new_doc,
		):
			saved = directory.save_profile(phone_number="+919800000000", whatsapp_account="ACC-1")

		new_doc.assert_not_called()
		doc.save.assert_not_called()
		self.assertFalse(saved["created"])
		self.assertEqual(saved["name"], "PROF-9")

	def test_recipient_list_update_requires_write(self):
		def allowed(doctype, ptype, doc=None, throw=False):
			ok = ptype == "read"
			if throw and not ok:
				_throw("no", frappe.PermissionError)
			return ok

		with (
			patch("nudg.services.directory._doctype_exists", return_value=True),
			patch("nudg.services.directory.frappe.db.exists", return_value=True),
			patch("nudg.services.directory.frappe.get_doc", return_value=MagicMock()),
			patch("nudg.services.directory.frappe.has_permission", side_effect=allowed),
			patch("nudg.services.directory.frappe.throw", side_effect=_throw),
		):
			with self.assertRaises(frappe.PermissionError):
				directory.save_recipient_list(name="VIP", list_name="VIP", recipients=[])
