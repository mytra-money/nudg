# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

"""Opt-in, opt-out, and STOP/START consent management service."""

from __future__ import annotations

import logging
import re
from typing import Any

import frappe
from frappe import _

from nudg.integrations.repository.contact_repo import DeskContactRepository

logger = logging.getLogger("nudg.services.consent")

# Standard Meta, CTIA, and global carrier compliance keywords
OPT_OUT_KEYWORDS = frozenset({
	"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "ARRET", "OPTOUT", "BLOCK", "REVOKE"
})
OPT_IN_KEYWORDS = frozenset({
	"START", "UNSTOP", "OPTIN", "SUBSCRIBE", "YES"
})


def evaluate_consent_keyword(text: str | None) -> tuple[str | None, str | None]:
	"""Evaluate whether incoming text matches an opt-out or opt-in consent keyword.

	Strips leading/trailing punctuation and whitespace, handles case-insensitivity.

	Returns:
		(new_consent_status, matched_keyword) or (None, None)
	"""
	if not text:
		return None, None

	# Normalize text: strip punctuation around words, uppercase
	cleaned = str(text).strip()
	normalized = re.sub(r"^[^\w]+|[^\w]+$", "", cleaned).upper()
	if not normalized:
		return None, None

	words = normalized.split()
	if len(words) == 1:
		word = words[0]
		if word in OPT_OUT_KEYWORDS:
			return "Opted-Out", word
		if word in OPT_IN_KEYWORDS:
			return "Opted-In", word

	return None, None


def handle_incoming_consent(
	contact_id: str,
	text: str,
	channel_doc: Any = None,
	phone_number: str | None = None,
	send_acknowledgment: bool = True,
) -> tuple[bool, str | None]:
	"""Check incoming message for consent keywords and update contact status.

	If matched, updates repository consent and optionally sends an immediate
	compliance acknowledgment text back to the customer.

	Returns:
		(is_consent_keyword, updated_status)
	"""
	new_status, keyword = evaluate_consent_keyword(text)
	if not new_status:
		return False, None

	reason = "STOP keyword" if new_status == "Opted-Out" else "START keyword"
	DeskContactRepository.update_consent(contact_id, new_status, reason=reason)

	# Realtime event
	frappe.publish_realtime(
		"nudg_consent_updated",
		{
			"contact_id": contact_id,
			"consent_status": new_status,
			"reason": reason,
		},
	)

	# Send immediate compliance acknowledgment if configured
	if send_acknowledgment and channel_doc:
		recipient = phone_number or _resolve_phone_number(contact_id)
		if recipient:
			_send_consent_acknowledgment(channel_doc, recipient, new_status)

	return True, new_status


def is_contact_opted_out(contact_id: str) -> bool:
	"""Check if a contact is currently opted out.

	Used by broadcast campaigns and messaging rules to prevent non-compliant sends.
	"""
	if not contact_id:
		return False

	if frappe.db.exists("DocType", "WA Profile") and frappe.db.exists("WA Profile", contact_id):
		if frappe.db.has_column("WA Profile", "consent_status"):
			status = frappe.db.get_value("WA Profile", contact_id, "consent_status")
			if str(status).lower() in ("opted-out", "opt-out", "unsubscribed", "blocked"):
				return True

	return False


def set_consent_status(
	contact_id: str,
	consent_status: str,
	reason: str | None = "Manual agent update",
) -> None:
	"""Explicitly update a contact's consent status (e.g. from Desk Contact profile)."""
	valid_statuses = {"Opted-In", "Opted-Out", "Pending"}
	if consent_status not in valid_statuses:
		frappe.throw(_("Invalid consent status '{0}'. Must be one of {1}.").format(consent_status, valid_statuses))

	DeskContactRepository.update_consent(contact_id, consent_status, reason=reason)
	frappe.publish_realtime(
		"nudg_consent_updated",
		{
			"contact_id": contact_id,
			"consent_status": consent_status,
			"reason": reason,
		},
	)


def _resolve_phone_number(contact_id: str) -> str | None:
	if frappe.db.exists("DocType", "WA Profile") and frappe.db.exists("WA Profile", contact_id):
		return frappe.db.get_value("WA Profile", contact_id, "phone_number")
	return contact_id if contact_id.startswith("+") or contact_id.isdigit() else None


def _send_consent_acknowledgment(channel_doc: Any, to: str, consent_status: str) -> None:
	try:
		if consent_status == "Opted-Out":
			ack_text = "You have successfully unsubscribed and will no longer receive messages. Reply START to resubscribe."
		else:
			ack_text = "You have successfully subscribed to receive messages. Reply STOP at any time to unsubscribe."

		from nudg.integrations.connector.factory import get_connector
		connector = get_connector(channel_doc)
		connector.send_text(channel_doc, to=to, text=ack_text)
	except Exception as exc:
		logger.warning(f"Could not dispatch consent acknowledgment: {exc}")
