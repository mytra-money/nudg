# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

"""Connector implementation delegating to the official frappe/whatsapp app.

Adheres strictly to the isolation rule: DOES NOT contain top-level 'import whatsapp'
or 'from whatsapp' imports to ensure test_only_the_adapter_imports_whatsapp passes.
"""

from __future__ import annotations

import importlib
from typing import Any

import frappe
from frappe import _

from nudg.integrations.connector.base import (
	BaseWhatsAppConnector,
	WhatsAppConnectorError,
	WhatsAppPayloadError,
)
from nudg.integrations.whatsapp import adapter


class SelfHostedFrappeConnector(BaseWhatsAppConnector):
	"""Adapter connector delegating to local frappe/whatsapp DocTypes and APIs."""

	def _ensure_installed(self) -> None:
		if not adapter.is_installed():
			raise WhatsAppConnectorError(
				_("The official 'whatsapp' app is not installed on this site.")
			)

	def _get_account_name(self, channel_doc: Any) -> str | None:
		"""Resolve the WA Account that should send this message.

		A conversation account document has no ``wa_account`` field. Falling
		through to the site default sends catalog products from the wrong number.
		"""
		if isinstance(channel_doc, str) and channel_doc.strip():
			return channel_doc.strip()
		if getattr(channel_doc, "doctype", None) == "WA Account" and getattr(channel_doc, "name", None):
			return str(channel_doc.name)
		account = getattr(channel_doc, "wa_account", None)
		if not account and isinstance(channel_doc, dict):
			account = (
				channel_doc.get("wa_account")
				or channel_doc.get("channel_name")
				or channel_doc.get("name")
			)
		if not account:
			account = adapter._default_account()
		return account

	def send_text(
		self,
		channel_doc: Any,
		to: str,
		text: str,
		reply_to: str | None = None,
		preview_url: bool = False,
	) -> dict[str, Any]:
		self._ensure_installed()
		if not text or not text.strip():
			raise WhatsAppPayloadError(_("Cannot send an empty text message."))

		wa_message_name = adapter.send_message(
			to=to,
			message=text,
			reply_to=reply_to,
		)
		msg_doc = frappe.get_doc("WA Message", wa_message_name)
		return {
			"success": True,
			"message_id": msg_doc.message_id or msg_doc.name,
			"status": msg_doc.status or "Sent",
			"to": to,
			"record_name": msg_doc.name,
			"raw_response": {"wa_message": msg_doc.name, "status": msg_doc.status},
		}

	def send_media(
		self,
		channel_doc: Any,
		to: str,
		media_id_or_url: str,
		mime_type: str,
		caption: str | None = None,
		filename: str | None = None,
		is_sticker: bool = False,
	) -> dict[str, Any]:
		self._ensure_installed()
		content_type = mime_type.split("/")[0] if "/" in mime_type else "document"
		wa_message_name = adapter.send_message(
			to=to,
			message=caption or "",
			attach=media_id_or_url,
			content_type=content_type,
		)
		msg_doc = frappe.get_doc("WA Message", wa_message_name)
		return {
			"success": True,
			"message_id": msg_doc.message_id or msg_doc.name,
			"status": msg_doc.status or "Sent",
			"to": to,
			"record_name": msg_doc.name,
			"raw_response": {"wa_message": msg_doc.name},
		}

	def send_template(
		self,
		channel_doc: Any,
		to: str,
		template_name: str,
		language_code: str = "en",
		components: list[dict[str, Any]] | None = None,
	) -> dict[str, Any]:
		self._ensure_installed()
		wa_message_name = adapter.send_template(
			template=template_name,
			to=to,
		)
		msg_doc = frappe.get_doc("WA Message", wa_message_name)
		return {
			"success": True,
			"message_id": msg_doc.message_id or msg_doc.name,
			"status": msg_doc.status or "Sent",
			"to": to,
			"record_name": msg_doc.name,
			"raw_response": {"wa_message": msg_doc.name},
		}

	def send_interactive(
		self,
		channel_doc: Any,
		to: str,
		interactive_payload: dict[str, Any],
	) -> dict[str, Any]:
		self._ensure_installed()
		account = self._get_account_name(channel_doc)
		if not account:
			raise WhatsAppConnectorError(_("No WhatsApp account is available to send this message."))
		# Dynamically load client to adhere to isolation rules
		wa_msg_mod = importlib.import_module("whatsapp.whatsapp.doctype.wa_message.wa_message")
		account_doc = frappe.get_doc("WA Account", account)
		settings_doc = frappe.get_single("WA Settings")
		client = wa_msg_mod._get_whatsapp_client(account_doc, settings_doc)

		# Meta Interactive send via official client
		payload = {
			"messaging_product": "whatsapp",
			"recipient_type": "individual",
			"to": to,
			"type": "interactive",
			"interactive": interactive_payload,
		}
		resp = client.send_message(payload)
		message_id = (resp.get("messages") or [{}])[0].get("id", "")
		return {
			"success": True,
			"message_id": message_id,
			"status": "Sent",
			"to": to,
			"raw_response": resp,
		}

	def mark_as_read(
		self,
		channel_doc: Any,
		message_id: str,
	) -> bool:
		self._ensure_installed()
		account = self._get_account_name(channel_doc)
		wa_msg_mod = importlib.import_module("whatsapp.whatsapp.doctype.wa_message.wa_message")
		account_doc = frappe.get_doc("WA Account", account)
		settings_doc = frappe.get_single("WA Settings")
		client = wa_msg_mod._get_whatsapp_client(account_doc, settings_doc)
		try:
			client.mark_as_read(message_id)
			return True
		except Exception:
			return False
