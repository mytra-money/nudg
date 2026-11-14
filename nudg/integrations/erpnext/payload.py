# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Pure helpers for ERPNext webhook payloads, signatures, and replay decisions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from typing import Any

FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALLOWED_EVENTS = frozenset({"after_insert", "on_update", "on_submit", "on_cancel"})
MAX_BODY_BYTES = 200_000
PHONE_FALLBACKS = ("contact_mobile", "mobile_no", "customer_mobile", "contact_phone", "phone")

# Replay outcomes. The first successful send for a document event is kept.
ACCEPT = "accept"
DUPLICATE = "duplicate"
CONFLICT = "conflict"
REQUEUE = "requeue"


class PayloadError(ValueError):
	"""The ERPNext event cannot be accepted as a WhatsApp send."""


def assert_field_name(value: str | None, label: str) -> str:
	name = (value or "").strip()
	if not FIELD_NAME.match(name):
		raise PayloadError(f"{label} must be a single field name.")
	return name


def assert_plain_label(value: str | None, label: str) -> str:
	"""Reject labels that would be interpreted when placed in a Jinja webhook body."""
	text = (value or "").strip()
	if not text or any(char in text for char in "{}\r\n"):
		raise PayloadError(f"{label} contains characters that are not allowed.")
	return text


def parse_field_list(value: str | None) -> list[str]:
	if not value or not str(value).strip():
		return []
	fields = []
	for part in str(value).split(","):
		name = part.strip()
		if not name:
			continue
		fields.append(assert_field_name(name, "Variable field"))
	return fields


def condition_matches(expression: str | None, doc: dict | None) -> bool:
	"""Match a conjunction of field=value checks. Never evaluates the expression."""
	text = (expression or "").strip()
	if not text:
		return True
	doc = doc or {}
	for part in text.split("&"):
		piece = part.strip()
		if "=" not in piece:
			return False
		key, expected = piece.split("=", 1)
		key = key.strip()
		if not FIELD_NAME.match(key):
			return False
		if str(doc.get(key) if doc.get(key) is not None else "") != expected.strip():
			return False
	return True


def normalize_recipient(number: str | None) -> str:
	digits = re.sub(r"\D", "", str(number or ""))
	if digits.startswith("00"):
		digits = digits[2:]
	return digits


def recipient_is_usable(number: str | None) -> bool:
	digits = normalize_recipient(number)
	return 8 <= len(digits) <= 15


def phone_from_event(body: dict, phone_field: str | None) -> str:
	explicit = body.get("phone")
	if recipient_is_usable(explicit):
		return normalize_recipient(explicit)
	doc = body.get("doc") if isinstance(body.get("doc"), dict) else {}
	candidates = []
	if phone_field:
		candidates.append(phone_field)
	candidates.extend(PHONE_FALLBACKS)
	seen = set()
	for field in candidates:
		if field in seen or not FIELD_NAME.match(field):
			continue
		seen.add(field)
		value = doc.get(field)
		if recipient_is_usable(value):
			return normalize_recipient(value)
	return ""


def variables_from_event(body: dict, fields: list[str]) -> dict[str, str]:
	supplied = body.get("variables") if isinstance(body.get("variables"), dict) else {}
	doc = body.get("doc") if isinstance(body.get("doc"), dict) else {}
	values: dict[str, str] = {}
	for field in fields:
		raw = supplied.get(field, doc.get(field, ""))
		if raw is None:
			raw = ""
		values[field] = str(raw)
	return values


def idempotency_key(site: str, doctype: str, name: str, event: str, rule: str) -> str:
	return f"{site}:{doctype}:{name}:{event}:{rule}"


def payload_fingerprint(body: dict[str, Any]) -> str:
	material = {
		"doctype": body.get("doctype") or "",
		"name": body.get("name") or "",
		"event": body.get("event") or "",
		"template": body.get("template") or "",
		"phone": normalize_recipient(body.get("phone")),
		"link": str(body.get("link") or ""),
		"variables": body.get("variables") if isinstance(body.get("variables"), dict) else {},
	}
	encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
	return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def sign_body(secret: str, body: bytes) -> str:
	digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
	return base64.b64encode(digest).decode("ascii")


def signatures_match(secret: str, body: bytes, header: str | None) -> bool:
	if not secret or not header:
		return False
	expected = sign_body(secret, body)
	return hmac.compare_digest(expected, str(header).strip())


def token_matches(secret: str, presented: str | None) -> bool:
	if not secret or not presented:
		return False
	return hmac.compare_digest(secret, str(presented).strip())


def decide_replay(
	existing: dict | None,
	fingerprint: str,
	*,
	opted_out: bool,
) -> str:
	"""Decide what a repeated event for the same document rule should do.

	A message Meta already accepted is never sent again. A queued attempt with
	the same payload is left alone. A failed or still-unsent attempt can take
	a corrected payload, unless the customer has opted out.
	"""
	if not existing:
		return ACCEPT
	same = existing.get("payload_sha") == fingerprint
	already_sent = bool(existing.get("message_id")) or existing.get("status") == "Sent"
	if already_sent:
		return DUPLICATE if same else CONFLICT
	if opted_out or existing.get("skip_reason") == "opted_out":
		return DUPLICATE
	if existing.get("status") == "Accepted" and same:
		return DUPLICATE
	if existing.get("status") in {"Accepted", "Failed", "Skipped"}:
		return DUPLICATE if same else REQUEUE
	return DUPLICATE if same else CONFLICT


def webhook_json_template(
	site_name: str,
	event: str,
	phone_field: str,
	variable_fields: list[str],
	link_field: str | None = None,
) -> str:
	"""Jinja body installed on the ERPNext Webhook. Field names are already validated."""
	site_name = assert_plain_label(site_name, "Site name")
	if event not in ALLOWED_EVENTS:
		raise PayloadError("Choose a document event Nudge can receive.")
	phone_field = assert_field_name(phone_field, "Phone field")
	rendered_fields = []
	for field in variable_fields:
		field = assert_field_name(field, "Variable field")
		rendered_fields.append(f'"{field}": {{{{ doc.{field} | tojson }}}}')
	variables = "{ " + ", ".join(rendered_fields) + " }" if rendered_fields else "{}"
	link_line = ""
	if link_field:
		link_field = assert_field_name(link_field, "Link field")
		link_line = f'\n  "link": {{{{ doc.{link_field} | tojson }}}},'
	return (
		"{\n"
		f'  "site": {json.dumps(site_name)},\n'
		f'  "event": {json.dumps(event)},'
		f"{link_line}\n"
		'  "doctype": "{{ doc.doctype }}",\n'
		'  "name": "{{ doc.name }}",\n'
		f'  "phone": {{{{ doc.{phone_field} | tojson }}}},\n'
		f'  "variables": {variables}\n'
		"}\n"
	)


def webhook_document_name(site_name: str, rule_name: str) -> str:
	site_name = assert_plain_label(site_name, "Site name")
	rule_name = assert_plain_label(rule_name, "Rule name")
	raw = f"Nudge {site_name} {rule_name}"
	cleaned = re.sub(r"[^A-Za-z0-9 _.-]", "", raw).strip()
	return (cleaned or "Nudge Rule")[:140]


def classify_transport_failure(exc: BaseException) -> str:
	"""Return retryable, uncertain, or permanent for an outbound HTTP failure.

	A read timeout is uncertain because the remote server may already have
	accepted the request. Those are not retried automatically.
	"""
	import requests

	if isinstance(exc, (requests.ConnectTimeout, requests.ConnectionError)):
		return "retryable"
	if isinstance(exc, requests.ReadTimeout):
		return "uncertain"
	response = getattr(exc, "response", None)
	status = getattr(response, "status_code", None)
	if status in {408, 429, 500, 502, 503, 504}:
		return "retryable"
	if status is not None:
		return "permanent"
	if isinstance(exc, requests.Timeout):
		return "uncertain"
	return "permanent"
