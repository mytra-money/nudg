"""Turn stored Meta / WhatsApp error payloads into short user-facing text."""

from __future__ import annotations

import json


def format_error_message(raw: str | None) -> str | None:
	"""Reduce a stored WhatsApp error to a minimal, readable phrase.

	Customer agents should see clean, minimal error notices like 'Failed to send'
	rather than long technical stack traces or JSON payloads.
	"""
	if not raw:
		return raw

	text = str(raw).strip()
	if not text:
		return None

	try:
		data = json.loads(text)
	except (ValueError, TypeError):
		if "190" in text or "authentication" in text.lower():
			return "Error sending"
		return text if len(text) <= 50 else "Error sending"

	if isinstance(data, list):
		data = data[0] if data else {}

	if not isinstance(data, dict):
		if "190" in text or "authentication" in text.lower():
			return "Error sending"
		return text if len(text) <= 50 else "Error sending"

	error = data.get("error", data)
	if not isinstance(error, dict):
		if "190" in text or "authentication" in text.lower():
			return "Error sending"
		return text if len(text) <= 50 else "Error sending"

	code = error.get("code") or error.get("error_subcode")
	err_type = str(error.get("type") or "").lower()

	# Code 190 / OAuthException: Credentials invalid or expired
	if str(code) == "190" or err_type == "oauthexception":
		return "Error sending"

	# Code 131047: 24h window closed
	if str(code) == "131047":
		return "Template required"

	# Code 131030: Phone number not in test whitelist
	if str(code) == "131030":
		return "Recipient not in test list"

	return "Error sending"
