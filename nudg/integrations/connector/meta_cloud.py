# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Direct Meta WhatsApp Cloud API Connector (v18.0+ specification).

Operates with zero dependencies on frappe/whatsapp. Pure Python stdlib + requests.
Features:
- Requests Session with connection pooling
- Exponential backoff retry with jitter on HTTP 429 and HTTP 503
- Strict secret redaction from all exceptions and log entries
- Conforms to Meta Graph API v18.0+ payload schemas
"""

from __future__ import annotations

import datetime
from email.utils import parsedate_to_datetime
import json
import logging
import random
import re
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import frappe
from frappe import _

from nudg.integrations.connector.base import (
	BaseWhatsAppConnector,
	WhatsAppAuthError,
	WhatsAppConnectorError,
	WhatsAppNetworkError,
	WhatsAppPayloadError,
	WhatsAppRateLimitError,
)

logger = logging.getLogger("nudg.connector.meta_cloud")


def _redact_token_string(text: str | None) -> str:
	"""Redact Meta access tokens (EAAB...) from strings."""
	if not text:
		return ""
	return re.sub(r"EAAB\w+", "EAAB[REDACTED]", str(text))


def _redact_token_from_data(val: Any) -> Any:
	"""Recursively sanitize raw response structures to prevent token leakage."""
	if isinstance(val, str):
		return _redact_token_string(val)
	if isinstance(val, dict):
		return {k: _redact_token_from_data(v) for k, v in val.items()}
	if isinstance(val, (list, tuple)):
		return [_redact_token_from_data(item) for item in val]
	return val


def _parse_retry_after(retry_after: Any, default_delay: float) -> float:
	"""Safely parse RFC 7231 Retry-After header (float seconds or HTTP-date)."""
	if not retry_after or not isinstance(retry_after, (str, int, float)):
		return default_delay
	try:
		return max(0.0, float(retry_after))
	except (ValueError, TypeError):
		pass
	if isinstance(retry_after, str):
		try:
			target_dt = parsedate_to_datetime(retry_after)
			if target_dt.tzinfo is None:
				target_dt = target_dt.replace(tzinfo=datetime.timezone.utc)
			now_dt = datetime.datetime.now(datetime.timezone.utc)
			diff = (target_dt - now_dt).total_seconds()
			if diff > 0:
				return min(diff, 300.0)
		except Exception:
			pass
	return default_delay


class DirectMetaCloudApiConnector(BaseWhatsAppConnector):
	"""Direct HTTP client for Meta WhatsApp Business Cloud API v18.0+."""

	def __init__(self, timeout: tuple[float, float] = (5.0, 30.0)):
		self.timeout = timeout
		self.session = self._create_session()

	def _create_session(self) -> requests.Session:
		session = requests.Session()
		retries = Retry(
			total=3,
			backoff_factor=0.5,
			status_forcelist=[500, 502, 503, 504],
			raise_on_status=False,
		)
		adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=20)
		session.mount("https://", adapter)
		session.mount("http://", adapter)
		return session

	def _normalize_phone(self, phone: str) -> str:
		"""Strip non-digits to produce standard international recipient ID."""
		cleaned = re.sub(r"\D", "", phone or "")
		if not cleaned:
			raise WhatsAppPayloadError(_("Invalid recipient phone number: {0}").format(phone))
		return cleaned

	def _get_channel_field(self, channel_doc: Any, fieldname: str, default: Any = None) -> Any:
		if hasattr(channel_doc, "get_decrypted_password") and fieldname in ("access_token", "webhook_secret", "api_key", "inbound_secret"):
			val = channel_doc.get_decrypted_password(fieldname, raise_exception=False)
			if val:
				return val
		if hasattr(channel_doc, "get_password") and fieldname in ("access_token", "webhook_secret", "api_key", "inbound_secret"):
			try:
				val = channel_doc.get_password(fieldname, raise_exception=False)
				if val:
					return val
			except Exception:
				pass
		if hasattr(channel_doc, fieldname):
			val = getattr(channel_doc, fieldname)
			if val is not None and val != "":
				return val
		if isinstance(channel_doc, dict):
			val = channel_doc.get(fieldname, default)
			if val is not None and val != "":
				return val
		return default

	def _get_config(self, channel_doc: Any) -> tuple[str, str, str, str]:
		phone_number_id = self._get_channel_field(channel_doc, "phone_number_id")
		access_token = self._get_channel_field(channel_doc, "access_token")
		api_version = self._get_channel_field(channel_doc, "api_version", "v18.0")
		base_url = self._get_channel_field(channel_doc, "api_base_url", "https://graph.facebook.com")

		if not phone_number_id:
			raise WhatsAppPayloadError(_("Channel is missing required 'phone_number_id'."))
		if not access_token:
			raise WhatsAppAuthError(_("Channel is missing required 'access_token'."))

		base_url = str(base_url).rstrip("/")
		api_version = str(api_version).strip()
		return str(phone_number_id), str(access_token), api_version, base_url

	def _execute_request(
		self,
		method: str,
		url: str,
		access_token: str,
		json_payload: dict[str, Any] | None = None,
		max_rate_limit_retries: int = 3,
	) -> dict[str, Any]:
		headers = {
			"Authorization": f"Bearer {access_token}",
			"Content-Type": "application/json",
			"User-Agent": "Nudg/1.0",
		}

		retries = 0
		backoff = 0.5

		while True:
			try:
				response = self.session.request(
					method=method,
					url=url,
					headers=headers,
					json=json_payload,
					timeout=self.timeout,
				)
			except requests.exceptions.Timeout as exc:
				clean_exc = _redact_token_string(str(exc))
				raise WhatsAppNetworkError(_("Meta Cloud API request timed out: {0}").format(clean_exc))
			except requests.exceptions.RequestException as exc:
				clean_exc = _redact_token_string(str(exc))
				raise WhatsAppNetworkError(_("Meta Cloud API connection error: {0}").format(clean_exc))

			# Handle 429 Rate Limit and 503 Service Unavailable with exponential backoff and jitter
			if response.status_code in (429, 503):
				retries += 1
				if retries > max_rate_limit_retries:
					if response.status_code == 429:
						err_data = self._parse_error_body(response)
						raise WhatsAppRateLimitError(
							_("Meta WhatsApp rate limit exceeded after {0} retries.").format(retries),
							raw_response=err_data,
						)
					break
				resp_headers = getattr(response, "headers", None)
				retry_after = (
					resp_headers.get("Retry-After")
					if resp_headers and hasattr(resp_headers, "get")
					else None
				)
				jitter = random.uniform(0.05, 0.2)
				delay = _parse_retry_after(retry_after, backoff + jitter)
				time.sleep(delay)
				backoff *= 2.0
				continue

			break

		return self._handle_response(response)

	def _parse_error_body(self, response: requests.Response) -> dict[str, Any]:
		try:
			data = response.json()
		except Exception:
			text = getattr(response, "text", "") or ""
			data = {"raw_text": text[:500]}
		return _redact_token_from_data(data)

	def _handle_response(self, response: requests.Response) -> dict[str, Any]:
		data = self._parse_error_body(response)

		if response.status_code >= 400:
			error_obj = data.get("error", {})
			raw_text = getattr(response, "text", "") or ""
			msg = error_obj.get("message") or raw_text[:300]
			code = error_obj.get("code")
			subcode = error_obj.get("error_subcode")
			fbtrace_id = error_obj.get("fbtrace_id")

			# Redact any accidental tokens from error message
			msg = _redact_token_string(msg)

			if response.status_code in (401, 403) or code in (190, 100):
				raise WhatsAppAuthError(
					_("Meta API Authentication failed (code {0}): {1}").format(code, msg),
					error_code=code,
					raw_response=data,
				)
			elif response.status_code == 429 or code in (80007, 130429):
				raise WhatsAppRateLimitError(
					_("Meta API Rate limit reached: {0}").format(msg),
					error_code=code,
					raw_response=data,
				)
			elif response.status_code == 400:
				raise WhatsAppPayloadError(
					_("Meta API Payload error (code {0}, subcode {1}): {2}").format(code, subcode, msg),
					error_code=code,
					raw_response=data,
				)
			elif response.status_code >= 500:
				raise WhatsAppNetworkError(
					_("Meta Cloud API server error ({0}): {1} [trace: {2}]").format(response.status_code, msg, fbtrace_id),
					error_code=code,
					raw_response=data,
				)
			else:
				raise WhatsAppConnectorError(
					_("Meta Cloud API error ({0}): {1} [trace: {2}]").format(response.status_code, msg, fbtrace_id),
					error_code=code,
					raw_response=data,
				)

		return data

	def send_text(
		self,
		channel_doc: Any,
		to: str,
		text: str,
		reply_to: str | None = None,
		preview_url: bool = False,
	) -> dict[str, Any]:
		phone_number_id, access_token, api_version, base_url = self._get_config(channel_doc)
		normalized_to = self._normalize_phone(to)

		if not text or not text.strip():
			raise WhatsAppPayloadError(_("Cannot send an empty text message."))

		payload: dict[str, Any] = {
			"messaging_product": "whatsapp",
			"recipient_type": "individual",
			"to": normalized_to,
			"type": "text",
			"text": {
				"preview_url": bool(preview_url),
				"body": text,
			},
		}
		if reply_to:
			payload["context"] = {"message_id": reply_to}

		url = f"{base_url}/{api_version}/{phone_number_id}/messages"
		resp = self._execute_request("POST", url, access_token, payload)
		message_id = (resp.get("messages") or [{}])[0].get("id", "")

		return {
			"success": True,
			"message_id": message_id,
			"status": "Sent",
			"to": normalized_to,
			"raw_response": resp,
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
		phone_number_id, access_token, api_version, base_url = self._get_config(channel_doc)
		normalized_to = self._normalize_phone(to)

		# Detect media type category (ensure stickers take precedence over generic image/)
		clean_mime = (mime_type or "").strip().lower().split(";")[0].strip()
		media_type = "document"
		if is_sticker or clean_mime == "image/webp":
			media_type = "sticker"
		elif clean_mime.startswith("image/"):
			media_type = "image"
		elif clean_mime.startswith("video/"):
			media_type = "video"
		elif clean_mime.startswith("audio/"):
			media_type = "audio"

		media_object: dict[str, Any] = {}
		# If numeric string or valid Meta ID, send by ID; otherwise link
		if str(media_id_or_url).isdigit() or (len(str(media_id_or_url)) > 15 and not str(media_id_or_url).startswith(("http://", "https://", "/"))):
			media_object["id"] = str(media_id_or_url)
		else:
			media_object["link"] = str(media_id_or_url)

		if caption and media_type in ("image", "document", "video"):
			media_object["caption"] = caption
		if filename and media_type == "document":
			media_object["filename"] = filename

		payload = {
			"messaging_product": "whatsapp",
			"recipient_type": "individual",
			"to": normalized_to,
			"type": media_type,
			media_type: media_object,
		}

		url = f"{base_url}/{api_version}/{phone_number_id}/messages"
		resp = self._execute_request("POST", url, access_token, payload)
		message_id = (resp.get("messages") or [{}])[0].get("id", "")

		return {
			"success": True,
			"message_id": message_id,
			"status": "Sent",
			"to": normalized_to,
			"raw_response": resp,
		}

	def send_template(
		self,
		channel_doc: Any,
		to: str,
		template_name: str,
		language_code: str = "en",
		components: list[dict[str, Any]] | None = None,
	) -> dict[str, Any]:
		phone_number_id, access_token, api_version, base_url = self._get_config(channel_doc)
		normalized_to = self._normalize_phone(to)

		template_obj: dict[str, Any] = {
			"name": template_name,
			"language": {"code": language_code},
		}
		if components:
			template_obj["components"] = components

		payload = {
			"messaging_product": "whatsapp",
			"recipient_type": "individual",
			"to": normalized_to,
			"type": "template",
			"template": template_obj,
		}

		url = f"{base_url}/{api_version}/{phone_number_id}/messages"
		resp = self._execute_request("POST", url, access_token, payload)
		message_id = (resp.get("messages") or [{}])[0].get("id", "")

		return {
			"success": True,
			"message_id": message_id,
			"status": "Sent",
			"to": normalized_to,
			"raw_response": resp,
		}

	def send_interactive(
		self,
		channel_doc: Any,
		to: str,
		interactive_payload: dict[str, Any],
	) -> dict[str, Any]:
		phone_number_id, access_token, api_version, base_url = self._get_config(channel_doc)
		normalized_to = self._normalize_phone(to)

		payload = {
			"messaging_product": "whatsapp",
			"recipient_type": "individual",
			"to": normalized_to,
			"type": "interactive",
			"interactive": interactive_payload,
		}

		url = f"{base_url}/{api_version}/{phone_number_id}/messages"
		resp = self._execute_request("POST", url, access_token, payload)
		message_id = (resp.get("messages") or [{}])[0].get("id", "")

		return {
			"success": True,
			"message_id": message_id,
			"status": "Sent",
			"to": normalized_to,
			"raw_response": resp,
		}

	def mark_as_read(
		self,
		channel_doc: Any,
		message_id: str,
	) -> bool:
		phone_number_id, access_token, api_version, base_url = self._get_config(channel_doc)

		payload = {
			"messaging_product": "whatsapp",
			"status": "read",
			"message_id": message_id,
		}

		url = f"{base_url}/{api_version}/{phone_number_id}/messages"
		try:
			resp = self._execute_request("POST", url, access_token, payload)
			return bool(resp.get("success", True))
		except Exception as exc:
			logger.warning(f"Failed to send read receipt for {message_id}: {exc}")
			return False
