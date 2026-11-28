# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Edge cases for the ERPNext connection. These tests do not call Meta or a live site."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import requests

from nudg.integrations.erpnext.client import ERPNextClient, ERPNextClientError
from nudg.integrations.erpnext.deliver import ordered_body_parameters
from nudg.integrations.erpnext.payload import (
	ACCEPT,
	CONFLICT,
	DUPLICATE,
	REQUEUE,
	PayloadError,
	alert_from_webhook,
	classify_transport_failure,
	condition_matches,
	decide_replay,
	idempotency_key,
	parse_field_list,
	payload_fingerprint,
	phone_from_event,
	recipient_is_usable,
	sign_body,
	signatures_match,
	token_matches,
	webhook_document,
	webhook_document_name,
	webhook_json_template,
	webhook_static_value,
	webhook_update,
	webhook_variable_map,
)
from nudg.integrations.erpnext.safety import SiteURLError, validate_site_url


def _public_dns(host, port):
	return [(2, 1, 6, "", ("1.1.1.1", port))]


def _private_dns(host, port):
	return [(2, 1, 6, "", ("10.1.1.1", port))]


class TestSiteURL(unittest.TestCase):
	def test_public_https_is_canonical(self):
		url = validate_site_url("https://ERP.Example.com/app/", resolve=_public_dns)
		self.assertEqual(url, "https://erp.example.com/app")

	def test_http_private_and_credential_urls_are_rejected(self):
		with self.assertRaises(SiteURLError):
			validate_site_url("http://erp.example.com", resolve=_public_dns)
		with self.assertRaises(SiteURLError):
			validate_site_url("https://user:secret@erp.example.com", resolve=_public_dns)
		with self.assertRaises(SiteURLError):
			validate_site_url("https://localhost/app", resolve=_public_dns)
		with self.assertRaises(SiteURLError):
			validate_site_url("https://169.254.169.254/", resolve=_public_dns)
		with self.assertRaises(SiteURLError):
			validate_site_url("https://erp.example.com", resolve=_private_dns)

	def test_http_is_allowed_only_when_asked(self):
		url = validate_site_url("http://erp.example.com", allow_http=True, resolve=_public_dns)
		self.assertEqual(url, "http://erp.example.com")

	def test_loopback_is_allowed_only_for_a_local_developer_site(self):
		with self.assertRaises(SiteURLError):
			validate_site_url("http://127.0.0.1:8013", allow_http=True, resolve=_public_dns)
		url = validate_site_url(
			"http://127.0.0.1:8013",
			allow_http=True,
			allow_loopback=True,
			resolve=_public_dns,
		)
		self.assertEqual(url, "http://127.0.0.1:8013")


class TestPayload(unittest.TestCase):
	def test_signature_and_token(self):
		body = b'{"name":"SINV-0001"}'
		signature = sign_body("secret", body)
		self.assertTrue(signatures_match("secret", body, signature))
		self.assertFalse(signatures_match("secret", body, signature + "x"))
		self.assertFalse(signatures_match("secret", b"{}", signature))
		self.assertTrue(token_matches("secret", "secret"))
		self.assertFalse(token_matches("secret", "other"))
		self.assertFalse(token_matches("secret", ""))

	def test_phone_and_variables(self):
		body = {"phone": "+91 98765-43210", "variables": {"customer_name": "Acme"}, "doc": {}}
		self.assertEqual(phone_from_event(body, "contact_mobile"), "919876543210")
		self.assertTrue(recipient_is_usable("919876543210"))
		self.assertFalse(recipient_is_usable("12345"))
		missing = {"doc": {"mobile_no": "00 1 (415) 555-1212"}}
		self.assertEqual(phone_from_event(missing, "contact_mobile"), "14155551212")

	def test_condition_is_not_evaluated(self):
		doc = {"status": "Paid", "grand_total": 10}
		self.assertTrue(condition_matches("status=Paid", doc))
		self.assertFalse(condition_matches("status=Draft", doc))
		self.assertFalse(condition_matches("__import__('os').system('echo owned')", doc))
		self.assertFalse(condition_matches("status=Paid&missing=1", doc))

	def test_field_names_reject_paths_and_templates(self):
		with self.assertRaises(PayloadError):
			parse_field_list("customer.mobile_no")
		with self.assertRaises(PayloadError):
			webhook_json_template("{{ doc.owner }}", "on_submit", "mobile_no", [])
		template = webhook_json_template("Acme", "on_submit", "contact_mobile", ["customer_name"], "customer")
		self.assertIn("{{ doc.contact_mobile | tojson }}", template)
		self.assertIn("{{ doc.customer | tojson }}", template)
		self.assertIn('"site": "Acme"', template)
		self.assertNotIn("{{ doc.owner }}", template)

	def test_alert_webhook_renders_and_round_trips(self):
		from jinja2 import Environment

		raw = webhook_json_template(
			"Acme",
			"on_submit",
			"contact_mobile",
			template="invoice_ready",
			variables={"customer": "customer_name"},
		)
		self.assertEqual(webhook_static_value(raw, "template"), "invoice_ready")
		self.assertEqual(webhook_static_value(raw, "phone_field"), "contact_mobile")
		self.assertEqual(webhook_static_value(raw, "site"), "Acme")

		class Doc:
			doctype = "Sales Invoice"
			name = 'SINV-"1"'
			contact_mobile = "919876543210"
			customer_name = "Acme"

		body = json.loads(Environment().from_string(raw).render(doc=Doc()))
		self.assertEqual(body["template"], "invoice_ready")
		self.assertEqual(body["name"], 'SINV-"1"')
		self.assertEqual(body["phone"], "919876543210")
		self.assertEqual(body["variables"]["customer"], "Acme")

		document = webhook_document(
			name=webhook_document_name("Acme", "Sales Invoice on_submit"),
			site_name="Acme",
			doctype="Sales Invoice",
			event="on_submit",
			phone_field="contact_mobile",
			template="invoice_ready",
			variables={"customer": "customer_name"},
			request_url="https://nudg.example.com/api/method/nudg.integrations.erpnext.ingest.receive",
			secret="inbound-secret",
		)
		self.assertEqual(document["name"], "Nudge Acme Sales Invoice on_submit")
		self.assertEqual(document["webhook_headers"][0]["value"], "Acme")
		self.assertNotIn("webhook_doctype", webhook_update(document))
		alert = alert_from_webhook(document, "Acme")
		self.assertEqual(alert["doctype"], "Sales Invoice")
		self.assertEqual(alert["template"], "invoice_ready")
		self.assertEqual(alert["variables"], {"customer": "customer_name"})
		self.assertTrue(alert["enabled"])
		self.assertIsNone(alert_from_webhook(document, "Other"))

	def test_alert_stays_on_the_same_webhook_when_modified(self):
		original = webhook_document(
			name=webhook_document_name("Acme", "Sales Invoice on_submit"),
			site_name="Acme",
			doctype="Sales Invoice",
			event="on_submit",
			phone_field="contact_mobile",
			template="invoice_ready",
			variables={"customer": "customer_name"},
			request_url="https://nudg.example.com/api/method/nudg.integrations.erpnext.ingest.receive",
			secret="inbound-secret",
		)
		original["enabled"] = 0
		disabled = alert_from_webhook(original, "Acme")
		self.assertFalse(disabled["enabled"])
		self.assertEqual(disabled["doctype"], "Sales Invoice")

		changed = webhook_document(
			name=original["name"],
			site_name="Acme",
			doctype="Sales Invoice",
			event="on_submit",
			phone_field="mobile_no",
			template="invoice_cancelled",
			variables={"customer": "customer"},
			request_url=original["request_url"],
			secret="inbound-secret",
			enabled=False,
		)
		updated = webhook_update(changed)
		self.assertEqual(updated["enabled"], 0)
		self.assertNotIn("webhook_doctype", updated)
		self.assertNotIn("webhook_docevent", updated)
		merged = {**original, **updated}
		alert = alert_from_webhook(merged, "Acme")
		self.assertEqual(alert["name"], original["name"])
		self.assertEqual(alert["doctype"], "Sales Invoice")
		self.assertEqual(alert["event"], "on_submit")
		self.assertEqual(alert["phone_field"], "mobile_no")
		self.assertEqual(alert["template"], "invoice_cancelled")
		self.assertEqual(alert["variables"], {"customer": "customer"})
		self.assertFalse(alert["enabled"])
		self.assertEqual(webhook_variable_map(changed["webhook_json"]), {"customer": "customer"})
		with self.assertRaises(PayloadError):
			webhook_document(
				name="Nudg alert",
				site_name="Acme",
				doctype="Sales Invoice",
				event="on_trash",
				phone_field="contact_mobile",
				template="invoice_ready",
				variables={},
				request_url="https://nudg.example.com/api/method/nudg.integrations.erpnext.ingest.receive",
				secret="inbound-secret",
			)

	def test_replay_keeps_the_first_send(self):
		sent = {"status": "Sent", "payload_sha": "a", "message_id": "wamid.1", "skip_reason": ""}
		self.assertEqual(decide_replay(None, "a", opted_out=False), ACCEPT)
		self.assertEqual(decide_replay(sent, "a", opted_out=False), DUPLICATE)
		self.assertEqual(decide_replay(sent, "b", opted_out=False), CONFLICT)
		queued = {"status": "Accepted", "payload_sha": "a", "message_id": "", "skip_reason": ""}
		self.assertEqual(decide_replay(queued, "a", opted_out=False), DUPLICATE)
		self.assertEqual(decide_replay(queued, "b", opted_out=False), REQUEUE)
		failed = {"status": "Failed", "payload_sha": "a", "message_id": "", "skip_reason": ""}
		self.assertEqual(decide_replay(failed, "b", opted_out=False), REQUEUE)
		self.assertEqual(decide_replay(failed, "b", opted_out=True), DUPLICATE)
		opted = {"status": "Skipped", "payload_sha": "a", "message_id": "", "skip_reason": "opted_out"}
		self.assertEqual(decide_replay(opted, "b", opted_out=False), DUPLICATE)

	def test_fingerprint_ignores_dict_order(self):
		first = payload_fingerprint({"doctype": "Sales Invoice", "name": "SINV-1", "event": "on_submit", "phone": "+91", "variables": {"b": "2", "a": "1"}})
		second = payload_fingerprint({"variables": {"a": "1", "b": "2"}, "phone": "91", "event": "on_submit", "name": "SINV-1", "doctype": "Sales Invoice"})
		self.assertEqual(first, second)
		self.assertEqual(
			idempotency_key("Acme", "Sales Invoice", "SINV-1", "on_submit", "Acme-Invoice"),
			"Acme:Sales Invoice:SINV-1:on_submit:Acme-Invoice",
		)

	def test_transport_classification(self):
		self.assertEqual(classify_transport_failure(requests.ConnectionError("down")), "retryable")
		self.assertEqual(classify_transport_failure(requests.ReadTimeout("slow")), "uncertain")
		response = requests.Response()
		response.status_code = 429
		error = requests.HTTPError("busy")
		error.response = response
		self.assertEqual(classify_transport_failure(error), "retryable")
		response.status_code = 400
		self.assertEqual(classify_transport_failure(error), "permanent")

	def test_template_parameters_follow_variable_order(self):
		template = {"template_variables": [{"variable_name": "customer"}, {"variable_name": "total"}]}
		params = ordered_body_parameters(template, {"customer_name": "Acme", "grand_total": "1200"}, ["customer_name", "grand_total"])
		self.assertEqual(params, {"customer": "Acme", "total": "1200"})
		positional = ordered_body_parameters({}, {"grand_total": "10"}, ["grand_total"])
		self.assertEqual(positional, {"1": "10"})


class _Response:
	def __init__(self, status, body):
		self.status_code = status
		self.text = body
		self.content = body.encode()

	def json(self):
		return json.loads(self.text)


class TestClient(unittest.TestCase):
	def test_private_url_never_calls_the_transport(self):
		called = {"count": 0}

		def transport(*args, **kwargs):
			called["count"] += 1
			raise AssertionError("transport should not be called")

		with self.assertRaises(SiteURLError):
			ERPNextClient("https://127.0.0.1", "key", "secret", transport=transport)
		self.assertEqual(called["count"], 0)

	def test_error_body_redacts_the_token(self):
		def transport(*args, **kwargs):
			return _Response(500, "token abcdefghijklmnop failed")

		with patch("nudg.integrations.erpnext.client.validate_site_url", side_effect=lambda url, **kwargs: "https://erp.example.com"):
			client = ERPNextClient("https://erp.example.com", "key", "secret", transport=transport)
			with self.assertRaises(ERPNextClientError) as raised:
				client.get_logged_user()
		self.assertTrue(raised.exception.retryable)
		self.assertNotIn("abcdefghijklmnop", str(raised.exception))
		self.assertIn("[REDACTED]", str(raised.exception))

	def test_resource_paths_are_quoted_and_named_routes_keep_the_slash(self):
		seen = {}

		def transport(method, url, **kwargs):
			seen["method"] = method
			seen["url"] = url
			seen["json"] = kwargs.get("json")
			seen["params"] = kwargs.get("params")
			return _Response(200, json.dumps({"name": "Nudg Acme Sales Invoice on_submit"}))

		with patch("nudg.integrations.erpnext.client.validate_site_url", side_effect=lambda url, **kwargs: "https://erp.example.com"):
			client = ERPNextClient("https://erp.example.com", "key", "secret", transport=transport)
			client.insert_resource("Webhook", {"name": "Nudg Acme Sales Invoice on_submit"})
			self.assertEqual(seen["method"], "POST")
			self.assertEqual(seen["url"], "https://erp.example.com/api/resource/Webhook")
			client.update_resource("Webhook", "Nudg Acme Sales Invoice on_submit", {"enabled": 0})
			self.assertEqual(seen["method"], "PUT")
			self.assertEqual(
				seen["url"],
				"https://erp.example.com/api/resource/Webhook/Nudg%20Acme%20Sales%20Invoice%20on_submit/",
			)
			client.get_resources("Webhook", fields=["name"], filters=[["request_url", "like", "%receive%"]], limit=20)
			self.assertEqual(seen["method"], "GET")
			self.assertEqual(json.loads(seen["params"]["fields"]), ["name"])
			self.assertEqual(seen["params"]["limit_page_length"], 20)

	def test_resource_responses_unwrap_the_data_envelope(self):
		def transport(method, url, **kwargs):
			if method == "GET" and url.endswith("/Sales%20Invoice/"):
				return _Response(200, json.dumps({"data": {"name": "Sales Invoice", "is_submittable": 1, "fields": []}}))
			return _Response(200, json.dumps({"data": [{"name": "Webhook"}]}))

		with patch("nudg.integrations.erpnext.client.validate_site_url", side_effect=lambda url, **kwargs: "https://erp.example.com"):
			client = ERPNextClient("https://erp.example.com", "key", "secret", transport=transport)
			doc = client.get_resource("DocType", "Sales Invoice")
			self.assertEqual(doc["is_submittable"], 1)
			self.assertEqual(client.get_resources("Webhook", fields=["name"], limit=10), [{"name": "Webhook"}])


class TestOAuthConnectedApp(unittest.TestCase):
	def test_client_uses_bearer_token_and_redacts_it(self):
		seen = {}

		def transport(method, url, **kwargs):
			seen["headers"] = kwargs.get("headers") or {}
			return _Response(500, "Failed with token oauth_secret_token_999")

		with patch("nudg.integrations.erpnext.client.validate_site_url", side_effect=lambda url, **kwargs: "https://erp.example.com"):
			client = ERPNextClient(
				"https://erp.example.com",
				access_token="oauth_secret_token_999",
				transport=transport,
			)
			with self.assertRaises(ERPNextClientError) as raised:
				client.get_logged_user()
			self.assertEqual(seen["headers"].get("Authorization"), "Bearer oauth_secret_token_999")
			self.assertNotIn("oauth_secret_token_999", str(raised.exception))

	def test_oauth_client_for_site_uses_site_oauth_user_token(self):
		from types import SimpleNamespace
		from nudg.integrations.erpnext.service import _client_for_site

		token_doc = SimpleNamespace(
			access_token="fresh_token_123",
			get=lambda f: "fresh_token_123",
			get_password=lambda f: "fresh_token_123",
		)
		app_doc = SimpleNamespace(get_active_token=lambda user=None: token_doc if user == "manager@acme.com" else None)
		site = SimpleNamespace(
			account="WA-ACME",
			site_url="https://erp.acme.com",
			connected_app="CA-ACME",
			oauth_user="manager@acme.com",
		)

		with (
			patch("nudg.integrations.erpnext.service.frappe.get_doc", return_value=app_doc),
			patch("nudg.integrations.erpnext.service._allow_http", return_value=False),
			patch("nudg.integrations.erpnext.client.validate_site_url", side_effect=lambda url, **kwargs: "https://erp.acme.com"),
		):
			client = _client_for_site(site)
			self.assertIsNotNone(client)
			self.assertEqual(client.access_token, "fresh_token_123")

	def test_oauth_client_marks_error_on_refresh_failure(self):
		from types import SimpleNamespace
		from nudg.integrations.erpnext.service import _client_for_site

		def boom(user=None):
			raise RuntimeError("invalid_grant")

		app_doc = SimpleNamespace(get_active_token=boom)
		site = SimpleNamespace(
			account="WA-ACME",
			site_url="https://erp.acme.com",
			connected_app="CA-ACME",
			oauth_user="manager@acme.com",
		)

		with (
			patch("nudg.integrations.erpnext.service.frappe.get_doc", return_value=app_doc),
			patch("nudg.integrations.erpnext.service._mark_oauth_error") as mark_err,
		):
			client = _client_for_site(site)
			self.assertIsNone(client)
			mark_err.assert_called_once()
			self.assertEqual(mark_err.call_args[0][0], "WA-ACME")
