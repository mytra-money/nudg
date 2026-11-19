# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Whitelisted Inbound Webhook Receiver for Meta WhatsApp Cloud API.

Route: /api/method/nudg.integrations.webhook.handler
Alias: /api/method/nudg.integrations.webhook.receive

Supports:
- GET: Webhook challenge verification (hub.mode == "subscribe", hub.verify_token, hub.challenge)
- POST: Validates X-Hub-Signature-256 HMAC-SHA256 signature, deduplicates messages,
        resolves contact, emits realtime events, and applies STOP opt-outs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any
from werkzeug.wrappers import Response

import frappe
from frappe import _

from nudg.integrations.connector.factory import get_connector
from nudg.integrations.repository.contact_repo import DeskContactRepository
from nudg.integrations.repository.message_repo import DeskMessageRepository
from nudg.services import consent
from nudg.services.consent import OPT_IN_KEYWORDS, OPT_OUT_KEYWORDS

logger = logging.getLogger("nudg.integrations.webhook")


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def handler() -> Response | str:
	"""Entry point delegating to standard Frappe WhatsApp webhook handler.

	The raw payload is kept for this request so the chatbot can read button
	ids and WhatsApp Flow replies, which the official message row does not store.
	"""
	request = getattr(frappe.local, "request", None)
	method = getattr(request, "method", "GET") if request else "GET"
	if method == "GET":
		return _handle_verification()
	frappe.flags.nudg_webhook_payload = _peek_payload()
	try:
		from whatsapp.whatsapp.webhook import handler as wa_handler
		return wa_handler()
	except Exception:
		return _handle_event()


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def receive() -> Response | str:
	"""Alias delegating to standard Frappe WhatsApp webhook handler."""
	return handler()


def _handle_verification() -> Response:
	"""Respond to Meta's webhook subscription verification challenge."""
	args = getattr(frappe, "form_dict", {}) or {}
	mode = args.get("hub.mode")
	token = args.get("hub.verify_token")
	challenge = args.get("hub.challenge")

	if not mode and hasattr(frappe.local, "request") and hasattr(frappe.local.request, "args"):
		mode = frappe.local.request.args.get("hub.mode")
		token = frappe.local.request.args.get("hub.verify_token")
		challenge = frappe.local.request.args.get("hub.challenge")

	if mode != "subscribe" or not token or not challenge:
		return Response("Invalid verification request", status=400, mimetype="text/plain")

	verified = False
	if frappe.db.exists("DocType", "WA Settings"):
		settings_token = frappe.db.get_single_value("WA Settings", "webhook_verify_token")
		if settings_token and hmac.compare_digest(str(settings_token), str(token)):
			verified = True

	if not verified:
		logger.warning("Webhook verification failed: token mismatch")
		return Response("Verification token mismatch", status=403, mimetype="text/plain")

	logger.info("Webhook subscription verified successfully")
	# Return raw challenge string as text/plain
	return Response(str(challenge), status=200, mimetype="text/plain")


def _peek_payload() -> dict:
	"""Read the cached request body without consuming it for the official handler."""
	request = getattr(frappe.local, "request", None)
	raw = b""
	if request and hasattr(request, "get_data"):
		raw = request.get_data(cache=True, as_text=False) or b""
	if not raw:
		return {}
	try:
		parsed = json.loads(raw.decode("utf-8"))
	except Exception:
		return {}
	return parsed if isinstance(parsed, dict) else {}


def _handle_event() -> str:
	"""Process incoming Meta webhook events (messages, status updates)."""
	raw_body = b""
	request = getattr(frappe.local, "request", None)
	if request and hasattr(request, "get_data"):
		raw_body = request.get_data(as_text=False) or b""
		if not raw_body and hasattr(request, "get_data"):
			text_body = request.get_data(as_text=True)
			if text_body:
				raw_body = text_body.encode("utf-8")

	payload: dict[str, Any] = {}
	if raw_body:
		try:
			payload = json.loads(raw_body.decode("utf-8"))
		except Exception:
			payload = getattr(frappe.local, "form_dict", {}) or {}
	else:
		payload = getattr(frappe.local, "form_dict", {}) or {}

	# Extract phone_number_id metadata to resolve channel
	phone_number_id = _extract_phone_number_id(payload)
	channel_doc = _resolve_channel(phone_number_id)

	# Validate HMAC signature or SaaS secret if configured
	secret = _get_webhook_secret(channel_doc)
	if secret:
		_verify_signature(raw_body, secret, channel_doc)

	# Process all entries
	for entry in payload.get("entry", []):
		for change in entry.get("changes", []):
			field = change.get("field")
			value = change.get("value", {})
			if field == "messages":
				_process_messages_field(value, channel_doc)

	if hasattr(frappe, "response"):
		frappe.response.http_status_code = 200
		frappe.response["content_type"] = "text/plain"
	return "ok"


def _extract_phone_number_id(payload: dict) -> str | None:
	for entry in payload.get("entry", []):
		for change in entry.get("changes", []):
			val = change.get("value", {})
			meta = val.get("metadata", {})
			if meta.get("phone_number_id"):
				return str(meta["phone_number_id"])
	return None


def _resolve_channel(phone_number_id: str | None) -> Any:
	"""Resolve the WA Account that owns this phone number id."""
	if not frappe.db.exists("DocType", "WA Account"):
		return None
	try:
		account_name = None
		if phone_number_id:
			account_name = frappe.db.get_value("WA Account", {"phone_id": phone_number_id}, "name")
		if not account_name and frappe.db.exists("DocType", "WA Settings"):
			account_name = frappe.db.get_single_value("WA Settings", "default_account")
		if account_name and frappe.db.exists("WA Account", account_name):
			try:
				return frappe.get_cached_doc("WA Account", account_name)
			except Exception:
				return frappe.get_doc("WA Account", account_name)
	except Exception as exc:
		logger.warning(f"Failed to resolve WhatsApp account: {exc}")
	return None


def _get_webhook_secret(channel_doc: Any) -> str | None:
	"""Return webhook secret for channel (inbound secret for SaaS or webhook secret for Meta)."""
	if channel_doc:
		conn_type = getattr(channel_doc, "connector_type", None) or (
			channel_doc.get("connector_type") if isinstance(channel_doc, dict) else None
		)
		if conn_type == "SaaS Gateway / Webhook":
			if hasattr(channel_doc, "get_inbound_secret"):
				inbound_secret = channel_doc.get_inbound_secret(raise_exception=False)
				if inbound_secret:
					return inbound_secret
			elif isinstance(channel_doc, dict) and channel_doc.get("inbound_secret"):
				return channel_doc["inbound_secret"]

		if hasattr(channel_doc, "get_webhook_secret"):
			secret = channel_doc.get_webhook_secret(raise_exception=False)
			if secret:
				return secret
		if hasattr(channel_doc, "get_decrypted_password"):
			secret = channel_doc.get_decrypted_password("webhook_secret", raise_exception=False)
			if secret:
				return secret

	if frappe.db.exists("DocType", "WA Settings"):
		return frappe.db.get_single_value("WA Settings", "webhook_secret")
	return None


def _verify_signature(raw_body: bytes, secret: str, channel_doc: Any = None) -> None:
	"""Verify webhook authentication supporting Meta HMAC-SHA256 and SaaS Gateway tokens."""
	conn_type = None
	if channel_doc:
		conn_type = getattr(channel_doc, "connector_type", None) or (
			channel_doc.get("connector_type") if isinstance(channel_doc, dict) else None
		)

	# 1. Check direct SaaS Gateway headers if in SaaS mode
	if conn_type == "SaaS Gateway / Webhook":
		gateway_header = (
			frappe.get_request_header("X-Gateway-Secret", "")
			or frappe.get_request_header("X-Inbound-Secret", "")
			or ""
		)
		if gateway_header and hmac.compare_digest(gateway_header.strip(), secret.strip()):
			return

		auth_header = frappe.get_request_header("Authorization", "") or ""
		if auth_header.startswith("Bearer "):
			token = auth_header[len("Bearer "):].strip()
			if hmac.compare_digest(token, secret.strip()):
				return

	# 2. Check standard Meta HMAC signature (also supported in forwarded SaaS webhooks)
	header = frappe.get_request_header("X-Hub-Signature-256", "") or ""
	if not header.startswith("sha256="):
		raise frappe.AuthenticationError(_("Missing or malformed X-Hub-Signature-256 header."))

	expected_hash = header[len("sha256="):]
	computed_hash = hmac.new(
		secret.encode("utf-8"),
		raw_body,
		hashlib.sha256,
	).hexdigest()

	if not hmac.compare_digest(computed_hash, expected_hash):
		raise frappe.AuthenticationError(_("HMAC-SHA256 signature mismatch."))


def _process_messages_field(value: dict, channel_doc: Any) -> None:
	contacts = value.get("contacts", [])
	contact_profile = contacts[0].get("profile", {}) if contacts else {}

	# 1. Inbound messages
	for msg in value.get("messages", []):
		_process_incoming_message(msg, channel_doc, contact_profile)

	# 2. Status updates
	for status in value.get("statuses", []):
		_process_status_update(status, channel_doc)


def _process_incoming_message(msg: dict, channel_doc: Any, contact_profile: dict) -> None:
	message_id = msg.get("id")
	if not message_id:
		return

	# Idempotency / Deduplication
	if DeskMessageRepository.is_duplicate_message(message_id):
		logger.info(f"Duplicate webhook message {message_id} ignored.")
		return

	wa_id = msg.get("from", "")
	profile_name = contact_profile.get("name") or wa_id
	channel_name = channel_doc.name if channel_doc else ""

	# Contact Resolution
	contact_id = DeskContactRepository.get_or_create_contact(
		wa_id=wa_id,
		profile_name=profile_name,
		account_or_channel=channel_name,
	)

	# Persistence via repository
	saved = DeskMessageRepository.save_incoming_message(
		channel_name=channel_name,
		msg=msg,
		contact_id=contact_id,
		contact_name=profile_name,
	)

	consent.handle_incoming_consent(
		contact_id=contact_id,
		text=saved.get("content") or "",
		channel_doc=channel_doc,
		phone_number=wa_id,
		send_acknowledgment=True,
	)

	# Auto Read Receipts
	if channel_doc and getattr(channel_doc, "auto_read_receipts", False):
		try:
			connector = get_connector(channel_doc)
			connector.mark_as_read(channel_doc, message_id)
		except Exception as exc:
			logger.warning(f"Failed auto read receipt for {message_id}: {exc}")


def _process_status_update(status: dict, channel_doc: Any) -> None:
	message_id = status.get("id")
	raw_status = status.get("status")
	errors = status.get("errors")

	DeskMessageRepository.update_message_status(
		message_id=message_id,
		new_status_raw=raw_status,
		timestamp=status.get("timestamp"),
		errors=errors,
	)

	try:
		from nudg.services.campaigns import update_campaign_recipient_status
		update_campaign_recipient_status(message_id, raw_status, errors)
	except Exception:
		pass
