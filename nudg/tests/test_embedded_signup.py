# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import frappe

from nudg.integrations import embedded_signup


class TestEmbeddedSignup(unittest.TestCase):
	def test_redact_hides_token_and_code(self):
		raw = "failed EAAB1234567890 code=abcDEF123"
		cleaned = embedded_signup.redact(raw)
		self.assertNotIn("EAAB1234567890", cleaned)
		self.assertNotIn("abcDEF123", cleaned)
		self.assertIn("EAA[REDACTED]", cleaned)
		self.assertIn("code=[REDACTED]", cleaned)

	def test_user_message_hides_the_graph_sentence(self):
		raw = (
			"Unsupported post request. Object with ID '2436551013419081' does not exist, "
			"cannot be loaded due to missing permissions"
		)
		message = embedded_signup.user_message(raw)
		self.assertNotIn("2436551013419081", message)
		self.assertNotIn("graph", message.lower())
		self.assertIn("permissions", message.lower())

	def test_redact_hides_query_access_token(self):
		cleaned = embedded_signup.redact("failed access_token=EAABsupersecret")
		self.assertNotIn("EAABsupersecret", cleaned)
		self.assertIn("access_token=[REDACTED]", cleaned)

	@patch("nudg.integrations.embedded_signup.requests.request")
	def test_permission_error_retries_with_query_token(self, request):
		denied = MagicMock(status_code=400)
		denied.text = "denied"
		denied.json.return_value = {
			"error": {"message": "Unsupported post request. Object does not exist, missing permissions"}
		}
		ok = MagicMock(status_code=200)
		ok.json.return_value = {"success": True}
		request.side_effect = [denied, ok]
		result = embedded_signup._graph(
			"POST",
			"https://graph.facebook.com/v23.0/1/subscribed_apps",
			token="EAABCustomerToken",
		)
		self.assertEqual(result, {"success": True})
		self.assertEqual(request.call_args_list[1].kwargs["params"]["access_token"], "EAABCustomerToken")
		self.assertNotIn("Authorization", request.call_args_list[1].kwargs["headers"])

	def test_mobile_title_uses_the_number(self):
		self.assertEqual(embedded_signup._mobile_title("+1 555-010-6909"), "+15550106909")
		self.assertEqual(embedded_signup._mobile_title("15550106909"), "15550106909")
		self.assertEqual(embedded_signup._mobile_title(""), "")

	def test_pin_is_six_digits(self):
		pin = embedded_signup.make_pin()
		self.assertEqual(len(pin), 6)
		self.assertTrue(pin.isdigit())

	@patch("nudg.integrations.embedded_signup.requests.request")
	def test_exchange_code_returns_token(self, request):
		response = MagicMock(status_code=200)
		response.json.return_value = {"access_token": "EAABCustomerToken"}
		request.return_value = response
		token = embedded_signup.exchange_code("752752485429112", "secret", "one-time", "v23.0")
		self.assertEqual(token, "EAABCustomerToken")
		params = request.call_args.kwargs["params"]
		self.assertEqual(params["code"], "one-time")
		self.assertNotIn("access_token", params)

	@patch("nudg.integrations.embedded_signup.requests.request")
	def test_graph_error_does_not_include_the_code(self, request):
		response = MagicMock(status_code=400)
		response.text = "bad code=supersecret"
		response.json.return_value = {"error": {"message": "Invalid code=supersecret"}}
		request.return_value = response
		with self.assertRaises(embedded_signup.EmbeddedSignupError) as caught:
			embedded_signup.exchange_code("1", "secret", "supersecret", "v23.0")
		self.assertNotIn("supersecret", str(caught.exception))

	@patch("nudg.integrations.embedded_signup.frappe.throw", side_effect=frappe.ValidationError("missing"))
	def test_complete_signup_rejects_a_missing_code(self, _throw):
		with self.assertRaises(frappe.ValidationError):
			embedded_signup.complete_signup("")

	def test_current_app_secret_is_used(self):
		doc = MagicMock()
		doc.doctype = "WA Signup Settings"
		doc.get_password.return_value = "current-secret"
		with patch("frappe.utils.password.get_decrypted_password") as decrypt:
			self.assertEqual(embedded_signup._read_secret(doc), "current-secret")
		decrypt.assert_not_called()

	def test_secret_saved_before_rename_is_copied(self):
		doc = MagicMock()
		doc.doctype = "WA Signup Settings"
		doc.get_password.return_value = None

		def decrypt(doctype, name, fieldname="password", raise_exception=True):
			if doctype == "WhatsApp Signup Settings":
				return "legacy-secret"
			return None

		mock_db = MagicMock()
		mock_db.exists.return_value = True
		with (
			patch("frappe.utils.password.get_decrypted_password", side_effect=decrypt),
			patch("frappe.utils.password.set_encrypted_password") as store,
			patch("frappe.utils.password.remove_encrypted_password") as remove,
			patch.object(embedded_signup.frappe, "db", mock_db),
		):
			secret = embedded_signup._read_secret(doc)
		self.assertEqual(secret, "legacy-secret")
		store.assert_called_once_with("WA Signup Settings", "WA Signup Settings", "legacy-secret", "app_secret")
		remove.assert_called_once_with("WhatsApp Signup Settings", "WhatsApp Signup Settings", "app_secret")
