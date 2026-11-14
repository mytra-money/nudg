# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

"""Abstract base connector and standard exceptions for NUDG."""

from __future__ import annotations

import abc
from typing import Any


class WhatsAppConnectorError(Exception):
	"""Base exception for all WhatsApp connector errors."""

	def __init__(
		self,
		message: str,
		error_code: str | int | None = None,
		raw_response: dict | None = None,
	):
		super().__init__(message)
		self.message = message
		self.error_code = error_code
		self.raw_response = raw_response or {}


class WhatsAppAuthError(WhatsAppConnectorError):
	"""Authentication or permission error (HTTP 401 / 403 or OAuthException)."""

	pass


class WhatsAppRateLimitError(WhatsAppConnectorError):
	"""Rate limit exceeded (HTTP 429 or Meta code 80007 / 130429)."""

	def __init__(
		self,
		message: str,
		retry_after: int | float | None = None,
		**kwargs,
	):
		super().__init__(message, **kwargs)
		self.retry_after = retry_after


class WhatsAppNetworkError(WhatsAppConnectorError):
	"""Network connection failure, timeout, or 5xx server error."""

	pass


class WhatsAppPayloadError(WhatsAppConnectorError):
	"""Malformed request payload, invalid phone number, or unapproved template."""

	pass


# Backward-compatible and concise aliases
ConnectorError = WhatsAppConnectorError
AuthenticationError = WhatsAppAuthError
RateLimitError = WhatsAppRateLimitError


class BaseWhatsAppConnector(abc.ABC):
	"""Abstract interface defining the outbound WhatsApp messaging protocol."""

	@abc.abstractmethod
	def send_text(
		self,
		channel_doc: Any,
		to: str,
		text: str,
		reply_to: str | None = None,
		preview_url: bool = False,
	) -> dict[str, Any]:
		"""Send a plain text message.

		Args:
			channel_doc: WA Account or connector configuration dict.
			to: Recipient phone number (E.164 format, e.g. "+15551234567" or "15551234567").
			text: Body text of the message.
			reply_to: Optional message_id (wamid) of the message being replied to.
			preview_url: Whether to enable rich URL link preview card.

		Returns:
			dict containing:
				- success (bool): True
				- message_id (str): Meta message ID (wamid) or local record name
				- status (str): Initial message status ("Sent")
				- to (str): Normalized recipient phone number
				- raw_response (dict): Raw upstream response
		"""
		pass

	@abc.abstractmethod
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
		"""Send an image, audio, video, document, or sticker message.

		Args:
			channel_doc: WA Account or connector configuration dict.
			to: Recipient phone number.
			media_id_or_url: Meta media ID or accessible URL / File doc path.
			mime_type: MIME type (e.g. "image/jpeg", "application/pdf").
			caption: Optional caption text (supported on image, document, video).
			filename: Optional filename for document attachment.
			is_sticker: Explicit flag indicating whether the media is a sticker.
		"""
		pass

	@abc.abstractmethod
	def send_template(
		self,
		channel_doc: Any,
		to: str,
		template_name: str,
		language_code: str = "en",
		components: list[dict[str, Any]] | None = None,
	) -> dict[str, Any]:
		"""Send an approved WhatsApp Business template message.

		Args:
			channel_doc: WA Account or connector configuration dict.
			to: Recipient phone number.
			template_name: Registered Meta template name.
			language_code: Language code (e.g. "en_US", "es").
			components: Optional parameter components (header, body, buttons).
		"""
		pass

	@abc.abstractmethod
	def send_interactive(
		self,
		channel_doc: Any,
		to: str,
		interactive_payload: dict[str, Any],
	) -> dict[str, Any]:
		"""Send an interactive buttons, list, or catalog message.

		Args:
			channel_doc: WA Account or connector configuration dict.
			to: Recipient phone number.
			interactive_payload: Meta interactive specification dict.
		"""
		pass

	@abc.abstractmethod
	def mark_as_read(
		self,
		channel_doc: Any,
		message_id: str,
	) -> bool:
		"""Acknowledge and mark an incoming message as read.

		Args:
			channel_doc: WA Account or connector configuration dict.
			message_id: Inbound message ID (wamid).

		Returns:
			bool: True if read receipt was accepted.
		"""
		pass
