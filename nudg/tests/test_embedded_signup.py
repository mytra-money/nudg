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
