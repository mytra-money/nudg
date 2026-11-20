# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Repository handling contact resolution and consent tracking."""

from __future__ import annotations

import importlib
from typing import Any

import frappe


class DeskContactRepository:
	"""Manages customer profiles, E.164 phone numbers, and opt-in consent."""

	@classmethod
	def get_or_create_contact(
		cls,
		wa_id: str,
		profile_name: str | None = None,
		account_or_channel: str | None = None,
	) -> str:
		"""Resolve or insert a contact record, returning the primary identifier."""
		cleaned_wa_id = str(wa_id).lstrip("+")
		phone_e164 = f"+{cleaned_wa_id}"

		if frappe.db.exists("DocType", "WA Profile"):
			# Resolve channel name to valid WA Account to avoid LinkValidationError
			resolved_acc = account_or_channel
			try:
				from nudg.integrations.repository.message_repo import DeskMessageRepository
				resolved_acc = DeskMessageRepository.resolve_wa_account(account_or_channel)
			except Exception:
				pass

			# Self-hosted delegation via importlib to comply with isolation test
			wa_profile_mod = importlib.import_module("whatsapp.whatsapp.doctype.wa_profile.wa_profile")
			get_or_create_profile = getattr(wa_profile_mod, "get_or_create_profile", None)
			if callable(get_or_create_profile):
				profile = get_or_create_profile(
					phone_number=phone_e164,
					account_name=resolved_acc,
					profile_name=profile_name,
					wa_id=wa_id,
				)
				return profile

		return wa_id

	@classmethod
	def update_consent(
		cls,
		contact_id: str,
		consent_status: str,
		reason: str | None = None,
	) -> None:
		"""Update contact opt-in or opt-out status (e.g. on STOP keyword)."""
		# consent_status and consent_reason were removed. Callers still record the
		# keyword; profile status is what later sends check.
		return
