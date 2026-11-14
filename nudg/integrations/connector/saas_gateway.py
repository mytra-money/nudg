# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

"""SaaS Gateway / Managed Cloud Connector for NUDG.

Dispatches outbound messages and synchronizes templates via an external SaaS forwarder /
gateway API (e.g., Mytra Cloud Gateway, Lyqd SaaS Hub, or a managed Meta WABA proxy).

Features:
- Requests Session with connection pooling
- Exponential backoff retry with jitter on HTTP 429 and 503
- Strict API key and secret redaction from exceptions and log entries
- Dual-mode support: delegates to SaaS endpoint with tenant isolation headers
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
from urllib.parse import urljoin

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

logger = logging.getLogger("nudg.connector.saas_gateway")


def _redact_key_string(text: str | None) -> str:
	"""Redact API keys and bearer tokens from strings."""
	if not text:
		return ""
	# Redact Bearer tokens, long hex/alphanumeric keys
	cleaned = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", r"\1[REDACTED]", str(text))
	cleaned = re.sub(r"key-[A-Za-z0-9]{8,}", "key-[REDACTED]", cleaned)
	cleaned = re.sub(r"sk-[A-Za-z0-9]{8,}", "sk-[REDACTED]", cleaned)
	return cleaned


def _redact_data(val: Any) -> Any:
	"""Recursively sanitize raw response structures to prevent credential leakage."""
	if isinstance(val, str):
		return _redact_key_string(val)
	if isinstance(val, dict):
		return {k: _redact_data(v) for k, v in val.items()}
	if isinstance(val, (list, tuple)):
		return [_redact_data(item) for item in val]
	return val


class SaaSGatewayConnector(BaseWhatsAppConnector):
	"""Connector implementation communicating with an external SaaS Gateway / Hub."""

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

	# -------------------------------------------------------------------------
	# Configuration Extraction
	# -------------------------------------------------------------------------

	def _get_config(self, channel_doc: Any) -> dict[str, str]:
		"""Extract and validate SaaS gateway connection parameters."""
		if not channel_doc:
			raise WhatsAppConnectorError(_("No channel configuration provided."))

		gateway_url = None
		api_key = None
		channel_name = None

		if hasattr(channel_doc, "gateway_url"):
			gateway_url = channel_doc.gateway_url
		elif isinstance(channel_doc, dict):
			gateway_url = channel_doc.get("gateway_url")

		if hasattr(channel_doc, "get_api_key"):
			api_key = channel_doc.get_api_key(raise_exception=False)
		elif hasattr(channel_doc, "api_key"):
			api_key = channel_doc.api_key
		elif isinstance(channel_doc, dict):
			api_key = channel_doc.get("api_key")

		if hasattr(channel_doc, "channel_name"):
			channel_name = channel_doc.channel_name
		elif isinstance(channel_doc, dict):
			channel_name = channel_doc.get("channel_name")

		if not gateway_url:
			raise WhatsAppConnectorError(
				_("SaaS Gateway URL is not configured on channel '{0}'.").format(channel_name or "Default")
			)

		if not api_key:
			raise WhatsAppAuthError(
				_("SaaS Gateway API Key is missing on channel '{0}'.").format(channel_name or "Default")
			)

		return {
			"gateway_url": gateway_url.rstrip("/"),
			"api_key": str(api_key),
			"channel_name": channel_name or "default",
		}

	def _get_headers(self, config: dict[str, str]) -> dict[str, str]:
		site = (
			frappe.local.site
			if getattr(frappe, "local", None) and hasattr(frappe.local, "site")
			else "default"
		)
		return {
			"Authorization": f"Bearer {config['api_key']}",
			"Content-Type": "application/json",
			"Accept": "application/json",
			"X-Channel-Name": config["channel_name"],
			"X-Frappe-Site": str(site),
		}

	# -------------------------------------------------------------------------
	# HTTP Request with Exponential Backoff
	# -------------------------------------------------------------------------

	def _request(
		self,
		method: str,
		url: str,
		headers: dict[str, str],
		json_payload: dict[str, Any] | None = None,
		max_retries: int = 3,
	) -> dict[str, Any]:
		attempt = 0
		delay = 1.0

		while attempt < max_retries:
			attempt += 1
			try:
				response = self.session.request(
					method=method,
					url=url,
					headers=headers,
					json=json_payload,
					timeout=self.timeout,
				)

				# 1. Success response
				if response.status_code in (200, 201, 202):
					try:
						return response.json()
					except Exception:
						return {"status": "ok", "raw_text": response.text}

				# 2. Rate limit (429)
				if response.status_code == 429:
					if attempt >= max_retries:
						raise WhatsAppRateLimitError(
							_("SaaS Gateway rate limit exceeded. Please retry later."),
							raw_response=_redact_data(response.text),
						)
					time.sleep(delay + random.uniform(0.1, 0.5))
					delay *= 2
					continue

				# 3. Authentication failure (401 / 403)
				if response.status_code in (401, 403):
					error_msg = _("Authentication failed with SaaS Gateway (HTTP {0}). Check API Key.").format(
						response.status_code
					)
					raise WhatsAppAuthError(error_msg, raw_response=_redact_data(response.text))

				# 4. Bad request / payload error (400)
				if response.status_code == 400:
					try:
						err_json = response.json()
						msg = err_json.get("error", {}).get("message") or err_json.get("message") or response.text
					except Exception:
						msg = response.text
					raise WhatsAppPayloadError(
						_("SaaS Gateway rejected request: {0}").format(_redact_key_string(str(msg))),
						raw_response=_redact_data(response.text),
					)

				# 5. Gateway / server errors (502, 503, 504)
				if response.status_code in (502, 503, 504):
					if attempt >= max_retries:
						raise WhatsAppNetworkError(
							_("SaaS Gateway server temporarily unavailable (HTTP {0}).").format(response.status_code),
							raw_response=_redact_data(response.text),
						)
					time.sleep(delay)
					delay *= 2
					continue

				# General error
				raise WhatsAppConnectorError(
					_("SaaS Gateway error HTTP {0}: {1}").format(response.status_code, _redact_key_string(response.text)),
					raw_response=_redact_data(response.text),
				)

			except (requests.ConnectionError, requests.Timeout) as e:
				if attempt >= max_retries:
					raise WhatsAppNetworkError(
						_("Failed to connect to SaaS Gateway at {0}: {1}").format(url, _redact_key_string(str(e)))
					)
				time.sleep(delay)
				delay *= 2

		raise WhatsAppNetworkError(_("SaaS Gateway request failed after {0} attempts.").format(max_retries))

	# -------------------------------------------------------------------------
	# Outbound API Methods
	# -------------------------------------------------------------------------

	def send_text(
		self,
		channel_doc: Any,
		to: str,
		text: str,
		reply_to: str | None = None,
		preview_url: bool = False,
	) -> dict[str, Any]:
		"""Send text message via SaaS Gateway."""
		if not text or not text.strip():
			raise WhatsAppPayloadError(_("Cannot send an empty text message."))

		config = self._get_config(channel_doc)
		url = f"{config['gateway_url']}/api/v1/whatsapp/messages"
		headers = self._get_headers(config)

		payload: dict[str, Any] = {
			"to": to,
			"type": "text",
			"text": {
				"body": text,
				"preview_url": preview_url,
			},
		}
		if reply_to:
			payload["context"] = {"message_id": reply_to}

		result = self._request("POST", url, headers, json_payload=payload)
		message_id = (
			result.get("message_id")
			or (result.get("messages", [{}])[0].get("id") if result.get("messages") else None)
			or f"saas_{int(time.time()*1000)}"
		)

		return {
			"success": True,
			"message_id": message_id,
			"status": "Sent",
			"to": to,
			"raw_response": _redact_data(result),
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
		"""Send media message via SaaS Gateway."""
		config = self._get_config(channel_doc)
		url = f"{config['gateway_url']}/api/v1/whatsapp/messages"
		headers = self._get_headers(config)

		media_type = "document"
		if is_sticker:
			media_type = "sticker"
		elif mime_type.startswith("image/"):
			media_type = "image"
		elif mime_type.startswith("audio/"):
			media_type = "audio"
		elif mime_type.startswith("video/"):
			media_type = "video"

		media_obj: dict[str, Any] = {"link": media_id_or_url}
		if caption and media_type in ("image", "document", "video"):
			media_obj["caption"] = caption
		if filename and media_type == "document":
			media_obj["filename"] = filename

		payload: dict[str, Any] = {
			"to": to,
			"type": media_type,
			media_type: media_obj,
		}

		result = self._request("POST", url, headers, json_payload=payload)
		message_id = (
			result.get("message_id")
			or (result.get("messages", [{}])[0].get("id") if result.get("messages") else None)
			or f"saas_{int(time.time()*1000)}"
		)

		return {
			"success": True,
			"message_id": message_id,
			"status": "Sent",
			"to": to,
			"raw_response": _redact_data(result),
		}

	def send_template(
		self,
		channel_doc: Any,
		to: str,
		template_name: str,
		language_code: str = "en",
		components: list[dict[str, Any]] | None = None,
	) -> dict[str, Any]:
		"""Send pre-approved WhatsApp template via SaaS Gateway."""
		config = self._get_config(channel_doc)
		url = f"{config['gateway_url']}/api/v1/whatsapp/messages"
		headers = self._get_headers(config)

		payload: dict[str, Any] = {
			"to": to,
			"type": "template",
			"template": {
				"name": template_name,
				"language": {"code": language_code},
				"components": components or [],
			},
		}

		result = self._request("POST", url, headers, json_payload=payload)
		message_id = (
			result.get("message_id")
			or (result.get("messages", [{}])[0].get("id") if result.get("messages") else None)
			or f"saas_{int(time.time()*1000)}"
		)

		return {
			"success": True,
			"message_id": message_id,
			"status": "Sent",
			"to": to,
			"raw_response": _redact_data(result),
		}

	def send_interactive(
		self,
		channel_doc: Any,
		to: str,
		interactive_payload: dict[str, Any],
	) -> dict[str, Any]:
		"""Send interactive component message via SaaS Gateway."""
		config = self._get_config(channel_doc)
		url = f"{config['gateway_url']}/api/v1/whatsapp/messages"
		headers = self._get_headers(config)

		payload: dict[str, Any] = {
			"to": to,
			"type": "interactive",
			"interactive": interactive_payload,
		}

		result = self._request("POST", url, headers, json_payload=payload)
		message_id = (
			result.get("message_id")
			or (result.get("messages", [{}])[0].get("id") if result.get("messages") else None)
			or f"saas_{int(time.time()*1000)}"
		)

		return {
			"success": True,
			"message_id": message_id,
			"status": "Sent",
			"to": to,
			"raw_response": _redact_data(result),
		}

	def mark_as_read(
		self,
		channel_doc: Any,
		message_id: str,
	) -> bool:
		"""Acknowledge read receipt via SaaS Gateway."""
		try:
			config = self._get_config(channel_doc)
			url = f"{config['gateway_url']}/api/v1/whatsapp/messages"
			headers = self._get_headers(config)

			payload = {
				"status": "read",
				"message_id": message_id,
			}
			self._request("POST", url, headers, json_payload=payload)
			return True
		except Exception as e:
			logger.warning(f"Failed to submit read receipt to SaaS gateway: {_redact_key_string(str(e))}")
			return False

	# -------------------------------------------------------------------------
	# Management & Diagnostics
	# -------------------------------------------------------------------------

	def sync_templates(self, channel_doc: Any) -> list[dict[str, Any]]:
		"""Fetch approved templates provisioned on the SaaS Gateway."""
		config = self._get_config(channel_doc)
		url = f"{config['gateway_url']}/api/v1/whatsapp/templates"
		headers = self._get_headers(config)

		result = self._request("GET", url, headers)
		return result.get("data", []) or result.get("templates", [])

	def verify_credentials(self, channel_doc: Any) -> dict[str, Any]:
		"""Validate SaaS Gateway connectivity, quota, and tenant authorization."""
		config = self._get_config(channel_doc)
		url = f"{config['gateway_url']}/api/v1/whatsapp/health"
		headers = self._get_headers(config)

		try:
			result = self._request("GET", url, headers)
			return {
				"success": True,
				"gateway_url": config["gateway_url"],
				"status": result.get("status", "healthy"),
				"channel_name": config["channel_name"],
				"details": _redact_data(result),
			}
		except Exception as e:
			return {
				"success": False,
				"gateway_url": config["gateway_url"],
				"error": _redact_key_string(str(e)),
			}
