# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Hermetic Mock Meta WhatsApp Business Cloud API v18.0+ Environment.

Provides:
1. `MockWhatsAppCloudApi`: Reusable, standalone mock environment simulating Meta WhatsApp
   Business Cloud API v18.0+ endpoints, Authorization header verification, payload schema
   validation, and configurable error simulations (OAuth 190, Rate Limit 80007, 429/503
   with Retry-After headers).
2. Webhook payload generators for incoming text, media, interactive order cart, and status
   updates (sent, delivered, read, failed).
3. HMAC-SHA256 signature computation (X-Hub-Signature-256) using channel app secrets.
4. Requests adapter and context manager interface (`with MockWhatsAppCloudApi() as mock:`)
   intercepting live HTTP calls for hermetic offline test execution.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
from typing import Any, Callable
from unittest.mock import patch
import uuid

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger("nudg.tests.mock_cloud_api")


class MockWhatsAppCloudApiAdapter(HTTPAdapter):
	"""Custom requests HTTPAdapter that delegates requests to MockWhatsAppCloudApi."""

	def __init__(self, mock_api: MockWhatsAppCloudApi):
		super().__init__()
		self.mock_api = mock_api

	def send(
		self,
		request: requests.PreparedRequest,
		stream: bool = False,
		timeout: Any = None,
		verify: Any = True,
		cert: Any = None,
		proxies: Any = None,
	) -> requests.Response:
		return self.mock_api.handle_prepared_request(request)


class MockWhatsAppCloudApi:
	"""Standalone in-memory simulator for Meta WhatsApp Business Cloud API v18.0+.

	Supports:
	- Payload schema validation for text, template, interactive (SPM & MPM), media, and read receipts.
	- Bearer Authorization header validation.
	- Graph API error simulation modes:
	  * OAuthException code 190 (token expiry / invalid auth)
	  * Rate limit code 80007 (429 with Retry-After header)
	  * 503 Service Unavailable (with Retry-After header)
	  * Custom error responses and fail_count transients before recovery.
	- Recording of outbound calls and message history for assertion.
	- Webhook payload generation and HMAC-SHA256 signing for inbound testing.
	"""

	MESSAGE_URL_PATTERN = re.compile(
		r"^(?:https?://[^/]+)?(?:/v\d+\.\d+)?/([^/]+)/messages/?$"
	)

	def __init__(self, default_phone_number_id: str = "100200300"):
		self.default_phone_number_id = str(default_phone_number_id)
		self.requests_history: list[dict[str, Any]] = []
		self.sent_messages: list[dict[str, Any]] = []

		# Error simulation state
		self.error_mode: str | None = None
		self.error_status_code: int = 400
		self.error_response_body: dict[str, Any] = {}
		self.error_headers: dict[str, str] = {}
		self.error_fail_count: int = 0  # 0 = infinite until cleared
		self.error_calls_count: int = 0

		# Custom endpoint route handlers: list of (method, url_regex, handler_func)
		self.custom_handlers: list[tuple[str, re.Pattern, Callable[[str, dict, dict], tuple[int, dict, dict]]]] = []

		# Active patcher handle for context manager
		self._patchers: list[Any] = []
		self._is_active: bool = False

	# -------------------------------------------------------------------------
	# Context Manager & Lifecycle
	# -------------------------------------------------------------------------

	def __enter__(self) -> MockWhatsAppCloudApi:
		self.start()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb) -> None:
		self.stop()

	def start(self) -> MockWhatsAppCloudApi:
		"""Patch requests.Session.request to intercept all Meta Graph API calls."""
		if self._is_active:
			return self

		original_session_request = requests.Session.request

		def mocked_session_request(session_self, method, url, **kwargs):
			# Intercept Graph API calls or any calls targeted at Meta endpoints
			if self._should_intercept(str(url)):
				headers = kwargs.get("headers") or {}
				json_data = kwargs.get("json")
				data = kwargs.get("data")
				return self.dispatch_request(
					method=method,
					url=str(url),
					headers=headers,
					json_data=json_data,
					raw_data=data,
				)
			# Fallback to normal session request for any non-Meta requests
			return original_session_request(session_self, method, url, **kwargs)

		patcher = patch.object(requests.Session, "request", new=mocked_session_request)
		patcher.start()
		self._patchers.append(patcher)
		self._is_active = True
		return self

	def stop(self) -> None:
		"""Revert requests.Session patches."""
		while self._patchers:
			p = self._patchers.pop()
			p.stop()
		self._is_active = False

	def reset(self) -> None:
		"""Clear all recorded requests, sent messages, and error modes."""
		self.requests_history.clear()
		self.sent_messages.clear()
		self.clear_errors()

	def get_adapter(self) -> MockWhatsAppCloudApiAdapter:
		"""Return a requests HTTPAdapter that can be mounted on a Session."""
		return MockWhatsAppCloudApiAdapter(self)

	# -------------------------------------------------------------------------
	# Interception Logic
	# -------------------------------------------------------------------------

	def _should_intercept(self, url: str) -> bool:
		"""Check if URL targets Meta Graph API or message sending endpoint."""
		if "graph.facebook.com" in url:
			return True
		if self.MESSAGE_URL_PATTERN.search(url):
			return True
		for _, pattern, _ in self.custom_handlers:
			if pattern.search(url):
				return True
		return False

	def handle_prepared_request(self, request: requests.PreparedRequest) -> requests.Response:
		"""Handle PreparedRequest for HTTPAdapter."""
		json_data = None
		if request.body:
			try:
				if isinstance(request.body, bytes):
					json_data = json.loads(request.body.decode("utf-8"))
				elif isinstance(request.body, str):
					json_data = json.loads(request.body)
			except Exception:
				json_data = None

		return self.dispatch_request(
			method=request.method or "GET",
			url=request.url or "",
			headers=dict(request.headers),
			json_data=json_data,
			raw_data=request.body,
		)

	def dispatch_request(
		self,
		method: str,
		url: str,
		headers: dict[str, Any],
		json_data: dict[str, Any] | None = None,
		raw_data: Any = None,
	) -> requests.Response:
		"""Route request to appropriate mock handler and return requests.Response."""
		# Record incoming request in history
		record = {
			"method": method.upper(),
			"url": url,
			"headers": dict(headers),
			"json": json_data,
			"raw_data": raw_data,
			"timestamp": time.time(),
		}
		self.requests_history.append(record)

		# 1. Check custom handlers
		for custom_method, pattern, handler in self.custom_handlers:
			if custom_method.upper() == method.upper() and pattern.search(url):
				status_code, resp_body, resp_headers = handler(url, headers, json_data or {})
				return self._build_response(status_code, resp_body, resp_headers, url)

		# 2. Check if an active error mode triggers
		if self._should_simulate_error():
			self.error_calls_count += 1
			return self._build_response(
				self.error_status_code,
				self.error_response_body,
				self.error_headers,
				url,
			)

		# 3. Handle standard POST /{phone_number_id}/messages
		match = self.MESSAGE_URL_PATTERN.search(url)
		if match and method.upper() == "POST":
			phone_number_id = match.group(1)
			return self._handle_messages_endpoint(phone_number_id, headers, json_data or {}, url)

		# 4. Unknown endpoint fallback
		return self._build_response(
			404,
			{
				"error": {
					"message": f"(#803) Cannot query specified endpoint: {url}",
					"type": "OAuthException",
					"code": 803,
					"fbtrace_id": f"mock_trace_{uuid.uuid4().hex[:12]}",
				}
			},
			{},
			url,
		)

	# -------------------------------------------------------------------------
	# Message Endpoint Handler & Payload Validation
	# -------------------------------------------------------------------------

	def _handle_messages_endpoint(
		self,
		phone_number_id: str,
		headers: dict[str, Any],
		payload: dict[str, Any],
		url: str,
	) -> requests.Response:
		"""Process POST /{phone_number_id}/messages according to Meta v18.0 specs."""
		# 1. Validate Authorization Header
		auth_header = None
		for k, v in headers.items():
			if k.lower() == "authorization":
				auth_header = v
				break

		if not auth_header or not str(auth_header).startswith("Bearer "):
			return self._build_response(
				401,
				{
					"error": {
						"message": "Invalid OAuth access token - Cannot parse access token",
						"type": "OAuthException",
						"code": 190,
						"fbtrace_id": f"mock_trace_{uuid.uuid4().hex[:12]}",
					}
				},
				{},
				url,
			)

		token = str(auth_header)[len("Bearer "):].strip()
		if not token or token == "INVALID_TOKEN":
			return self._build_response(
				401,
				{
					"error": {
						"message": "Error validating access token: Session has expired or is invalid.",
						"type": "OAuthException",
						"code": 190,
						"error_subcode": 463,
						"fbtrace_id": f"mock_trace_{uuid.uuid4().hex[:12]}",
					}
				},
				{},
				url,
			)

		# 2. Check messaging_product
		if payload.get("messaging_product") != "whatsapp":
			return self._build_payload_error(
				url,
				"Field 'messaging_product' must be set to 'whatsapp'.",
			)

		# 3. Read receipt handler
		if payload.get("status") == "read":
			message_id = payload.get("message_id")
			if not message_id or not str(message_id).strip():
				return self._build_payload_error(url, "Field 'message_id' is required for read status updates.")
			return self._build_response(200, {"success": True}, {}, url)

		# 4. Message sending schema validation
		to = payload.get("to")
		if not to or not str(to).strip():
			return self._build_payload_error(url, "Field 'to' recipient is required.")

		msg_type = payload.get("type")
		if not msg_type:
			return self._build_payload_error(url, "Field 'type' is required.")

		validation_err = self._validate_payload_by_type(msg_type, payload)
		if validation_err:
			return self._build_payload_error(url, validation_err)

		# 5. Success response generation
		clean_to = re.sub(r"\D", "", str(to)) or str(to)
		generated_id = f"wamid.{uuid.uuid4().hex}"
		resp_data = {
			"messaging_product": "whatsapp",
			"contacts": [{"input": str(to), "wa_id": clean_to}],
			"messages": [{"id": generated_id}],
		}

		self.sent_messages.append({
			"message_id": generated_id,
			"phone_number_id": phone_number_id,
			"to": clean_to,
			"type": msg_type,
			"payload": payload,
			"timestamp": time.time(),
		})

		return self._build_response(200, resp_data, {}, url)

	def _validate_payload_by_type(self, msg_type: str, payload: dict[str, Any]) -> str | None:
		"""Validate payload according to Meta Cloud API v18.0 schemas."""
		if msg_type == "text":
			text_obj = payload.get("text")
			if not isinstance(text_obj, dict):
				return "Payload for type 'text' must contain an object named 'text'."
			body = text_obj.get("body")
			if not body or not str(body).strip():
				return "Text message 'body' cannot be empty."
			if len(str(body)) > 4096:
				return "Text message 'body' exceeds maximum length of 4096 characters."

		elif msg_type == "template":
			tmpl_obj = payload.get("template")
			if not isinstance(tmpl_obj, dict):
				return "Payload for type 'template' must contain an object named 'template'."
			if not tmpl_obj.get("name") or not str(tmpl_obj["name"]).strip():
				return "Template 'name' is required."
			lang = tmpl_obj.get("language")
			if not isinstance(lang, dict) or not lang.get("code"):
				return "Template 'language' must contain a valid 'code'."
			components = tmpl_obj.get("components")
			if components is not None:
				if not isinstance(components, list):
					return "Template 'components' must be a list."
				for comp in components:
					if not isinstance(comp, dict) or not comp.get("type"):
						return "Each component in template must be an object with a 'type'."

		elif msg_type == "interactive":
			interactive = payload.get("interactive")
			if not isinstance(interactive, dict):
				return "Payload for type 'interactive' must contain an object named 'interactive'."
			sub_type = interactive.get("type")
			if not sub_type:
				return "Interactive message requires a 'type' field."

			action = interactive.get("action")
			if not isinstance(action, dict):
				return "Interactive message requires an 'action' object."

			if sub_type == "product":
				# Single-Product Message (SPM)
				if not action.get("catalog_id"):
					return "Single-Product Message action requires 'catalog_id'."
				if not action.get("product_retailer_id"):
					return "Single-Product Message action requires 'product_retailer_id'."

			elif sub_type == "product_list":
				# Multi-Product Message (MPM)
				if not action.get("catalog_id"):
					return "Multi-Product Message action requires 'catalog_id'."
				sections = action.get("sections")
				if not isinstance(sections, list) or len(sections) == 0:
					return "Multi-Product Message action requires at least one section in 'sections'."
				if len(sections) > 10:
					return "Multi-Product Message can contain at most 10 sections."
				total_items = 0
				for sec in sections:
					if not isinstance(sec, dict) or not sec.get("title"):
						return "Each section in Multi-Product Message must contain a 'title'."
					if len(sec["title"]) > 24:
						return "Section title cannot exceed 24 characters."
					p_items = sec.get("product_items")
					if not isinstance(p_items, list) or len(p_items) == 0:
						return "Each section must contain 'product_items'."
					for it in p_items:
						if not isinstance(it, dict) or not it.get("product_retailer_id"):
							return "Each product item must specify 'product_retailer_id'."
						total_items += 1
				if total_items > 30:
					return f"Multi-Product Message exceeds maximum of 30 products (found {total_items})."

			elif sub_type == "button":
				buttons = action.get("buttons")
				if not isinstance(buttons, list) or len(buttons) == 0:
					return "Interactive button message requires at least one button."
				if len(buttons) > 3:
					return "Interactive button message supports at most 3 buttons."

			elif sub_type == "list":
				if not action.get("button"):
					return "Interactive list message requires an action button title."
				sections = action.get("sections")
				if not isinstance(sections, list) or len(sections) == 0:
					return "Interactive list message requires at least one section."

			else:
				return f"Unsupported interactive message type '{sub_type}'."

		elif msg_type in ("image", "audio", "document", "video", "sticker"):
			media_obj = payload.get(msg_type)
			if not isinstance(media_obj, dict):
				return f"Payload for media type '{msg_type}' must contain a '{msg_type}' object."
			media_id = media_obj.get("id")
			media_link = media_obj.get("link")
			if not media_id and not media_link:
				return f"Media object for '{msg_type}' must specify either 'id' or 'link'."

		else:
			return f"Unsupported message type: '{msg_type}'."

		return None

	def _build_payload_error(self, url: str, detail: str) -> requests.Response:
		"""Construct standard Meta v18.0 OAuthException 100 bad parameter response."""
		body = {
			"error": {
				"message": f"(#100) Invalid parameter: {detail}",
				"type": "OAuthException",
				"code": 100,
				"error_subcode": 2494010,
				"error_data": {
					"messaging_product": "whatsapp",
					"details": detail,
				},
				"fbtrace_id": f"mock_trace_{uuid.uuid4().hex[:12]}",
			}
		}
		return self._build_response(400, body, {}, url)

	def _build_response(
		self,
		status_code: int,
		body_dict: dict[str, Any],
		headers: dict[str, str],
		url: str,
	) -> requests.Response:
		"""Build genuine requests.Response object."""
		resp = requests.Response()
		resp.status_code = status_code
		resp._content = json.dumps(body_dict).encode("utf-8")
		resp.url = url
		resp.headers["Content-Type"] = "application/json"
		for k, v in headers.items():
			resp.headers[k] = str(v)
		return resp

	# -------------------------------------------------------------------------
	# Error Simulation Modes
	# -------------------------------------------------------------------------

	def _should_simulate_error(self) -> bool:
		if not self.error_mode:
			return False
		if self.error_fail_count > 0 and self.error_calls_count >= self.error_fail_count:
			# Error has completed its quota of failures; automatically clear
			self.clear_errors()
			return False
		return True

	def clear_errors(self) -> None:
		"""Reset error simulation modes to normal operating status."""
		self.error_mode = None
		self.error_status_code = 400
		self.error_response_body = {}
		self.error_headers.clear()
		self.error_fail_count = 0
		self.error_calls_count = 0

	def set_oauth_error(
		self,
		status_code: int = 401,
		code: int = 190,
		subcode: int = 463,
		message: str = "Error validating access token: Session has expired or is invalid.",
	) -> None:
		"""Simulate Meta OAuth authentication failure (e.g. invalid or revoked token)."""
		self.error_mode = "oauth_error"
		self.error_status_code = status_code
		self.error_fail_count = 0
		self.error_calls_count = 0
		self.error_headers.clear()
		self.error_response_body = {
			"error": {
				"message": message,
				"type": "OAuthException",
				"code": code,
				"error_subcode": subcode,
				"fbtrace_id": f"mock_trace_oauth_{uuid.uuid4().hex[:8]}",
			}
		}

	def set_rate_limit(
		self,
		code: int = 80007,
		retry_after: float | int | str = 0.05,
		fail_count: int = 1,
		message: str = "(#80007) There have been too many calls to this phone-number. Wait a bit and try again.",
	) -> None:
		"""Simulate Meta 429 rate limit with Retry-After header.

		Args:
			code: Meta error code (80007 or 130429).
			retry_after: Seconds to include in Retry-After header.
			fail_count: Number of times to return 429 before recovering (0 = forever).
		"""
		self.error_mode = "rate_limit"
		self.error_status_code = 429
		self.error_fail_count = fail_count
		self.error_calls_count = 0
		self.error_headers = {"Retry-After": str(retry_after)}
		self.error_response_body = {
			"error": {
				"message": message,
				"type": "OAuthException",
				"code": code,
				"error_subcode": 2494038,
				"fbtrace_id": f"mock_trace_rate_{uuid.uuid4().hex[:8]}",
			}
		}

	def set_service_unavailable(
		self,
		status_code: int = 503,
		retry_after: float | int | str = 0.05,
		fail_count: int = 1,
		message: str = "Service temporarily unavailable. Please retry shortly.",
	) -> None:
		"""Simulate 503 Service Unavailable with Retry-After header."""
		self.error_mode = "service_unavailable"
		self.error_status_code = status_code
		self.error_fail_count = fail_count
		self.error_calls_count = 0
		self.error_headers = {"Retry-After": str(retry_after)}
		self.error_response_body = {
			"error": {
				"message": message,
				"type": "OAuthException",
				"code": 2,
				"fbtrace_id": f"mock_trace_503_{uuid.uuid4().hex[:8]}",
			}
		}

	def set_custom_error(
		self,
		status_code: int,
		error_data: dict[str, Any],
		headers: dict[str, str] | None = None,
		fail_count: int = 1,
	) -> None:
		"""Set arbitrary failure response for specified number of requests."""
		self.error_mode = "custom_error"
		self.error_status_code = status_code
		self.error_fail_count = fail_count
		self.error_calls_count = 0
		self.error_headers = headers or {}
		self.error_response_body = error_data

	# -------------------------------------------------------------------------
	# Inspection Helpers
	# -------------------------------------------------------------------------

	def get_sent_messages(self) -> list[dict[str, Any]]:
		"""Return list of all successfully sent messages."""
		return list(self.sent_messages)

	def get_last_message(self) -> dict[str, Any] | None:
		"""Return most recently sent message dict or None."""
		return self.sent_messages[-1] if self.sent_messages else None

	def get_messages_for_recipient(self, to: str) -> list[dict[str, Any]]:
		"""Return all sent messages for a specific normalized phone number."""
		clean_to = re.sub(r"\D", "", to)
		return [m for m in self.sent_messages if m["to"] == clean_to]

	# -------------------------------------------------------------------------
	# Webhook Generators & Signature Helpers
	# -------------------------------------------------------------------------

	@staticmethod
	def compute_hub_signature(raw_body: bytes | str, secret: str) -> str:
		"""Compute Meta X-Hub-Signature-256 HMAC-SHA256 signature."""
		if isinstance(raw_body, str):
			raw_body = raw_body.encode("utf-8")
		if not isinstance(raw_body, (bytes, bytearray)):
			raw_body = str(raw_body).encode("utf-8")
		sig = hmac.new(secret.encode("utf-8"), bytes(raw_body), hashlib.sha256).hexdigest()
		return f"sha256={sig}"

	@classmethod
	def create_signed_webhook_payload(
		cls,
		payload: dict[str, Any],
		secret: str,
	) -> tuple[bytes, dict[str, str]]:
		"""Serialize payload and generate HMAC-SHA256 headers."""
		raw_bytes = json.dumps(payload).encode("utf-8")
		sig_header = cls.compute_hub_signature(raw_bytes, secret)
		headers = {
			"X-Hub-Signature-256": sig_header,
			"Content-Type": "application/json",
		}
		return raw_bytes, headers

	@classmethod
	def generate_text_webhook(
		cls,
		phone_number_id: str,
		from_wa_id: str,
		text: str,
		profile_name: str = "Alice Customer",
		message_id: str | None = None,
		timestamp: int | str | None = None,
	) -> dict[str, Any]:
		"""Generate standard Meta inbound text message webhook payload."""
		msg_id = message_id or f"wamid.IN_{uuid.uuid4().hex}"
		ts = str(timestamp or int(time.time()))
		clean_from = re.sub(r"\D", "", from_wa_id)

		return {
			"object": "whatsapp_business_account",
			"entry": [
				{
					"id": "WBA_100200",
					"changes": [
						{
							"field": "messages",
							"value": {
								"messaging_product": "whatsapp",
								"metadata": {
									"display_phone_number": "15551234567",
									"phone_number_id": str(phone_number_id),
								},
								"contacts": [
									{
										"profile": {"name": profile_name},
										"wa_id": clean_from,
									}
								],
								"messages": [
									{
										"from": clean_from,
										"id": msg_id,
										"timestamp": ts,
										"type": "text",
										"text": {"body": text},
									}
								],
							},
						}
					],
				}
			],
		}

	@classmethod
	def generate_media_webhook(
		cls,
		phone_number_id: str,
		from_wa_id: str,
		media_type: str,
		media_id: str = "MEDIA_998877",
		mime_type: str = "image/jpeg",
		caption: str | None = None,
		filename: str | None = None,
		profile_name: str = "Alice Customer",
		message_id: str | None = None,
		timestamp: int | str | None = None,
	) -> dict[str, Any]:
		"""Generate Meta inbound media (image, video, document, audio, sticker) webhook."""
		msg_id = message_id or f"wamid.MEDIA_{uuid.uuid4().hex}"
		ts = str(timestamp or int(time.time()))
		clean_from = re.sub(r"\D", "", from_wa_id)

		media_data: dict[str, Any] = {
			"id": media_id,
			"mime_type": mime_type,
		}
		if caption and media_type in ("image", "document", "video"):
			media_data["caption"] = caption
		if filename and media_type == "document":
			media_data["filename"] = filename

		return {
			"object": "whatsapp_business_account",
			"entry": [
				{
					"id": "WBA_100200",
					"changes": [
						{
							"field": "messages",
							"value": {
								"messaging_product": "whatsapp",
								"metadata": {
									"display_phone_number": "15551234567",
									"phone_number_id": str(phone_number_id),
								},
								"contacts": [
									{
										"profile": {"name": profile_name},
										"wa_id": clean_from,
									}
								],
								"messages": [
									{
										"from": clean_from,
										"id": msg_id,
										"timestamp": ts,
										"type": media_type,
										media_type: media_data,
									}
								],
							},
						}
					],
				}
			],
		}

	@classmethod
	def generate_order_cart_webhook(
		cls,
		phone_number_id: str,
		from_wa_id: str,
		catalog_id: str,
		product_items: list[dict[str, Any]],
		customer_text: str | None = "Please pack carefully",
		profile_name: str = "Alice Customer",
		message_id: str | None = None,
		timestamp: int | str | None = None,
	) -> dict[str, Any]:
		"""Generate Meta inbound order cart webhook payload."""
		msg_id = message_id or f"wamid.CART_{uuid.uuid4().hex}"
		ts = str(timestamp or int(time.time()))
		clean_from = re.sub(r"\D", "", from_wa_id)

		order_obj: dict[str, Any] = {
			"catalog_id": str(catalog_id),
			"product_items": product_items,
		}
		if customer_text:
			order_obj["text"] = customer_text

		return {
			"object": "whatsapp_business_account",
			"entry": [
				{
					"id": "WBA_100200",
					"changes": [
						{
							"field": "messages",
							"value": {
								"messaging_product": "whatsapp",
								"metadata": {
									"display_phone_number": "15551234567",
									"phone_number_id": str(phone_number_id),
								},
								"contacts": [
									{
										"profile": {"name": profile_name},
										"wa_id": clean_from,
									}
								],
								"messages": [
									{
										"from": clean_from,
										"id": msg_id,
										"timestamp": ts,
										"type": "order",
										"order": order_obj,
									}
								],
							},
						}
					],
				}
			],
		}

	@classmethod
	def generate_status_update_webhook(
		cls,
		phone_number_id: str,
		recipient_wa_id: str,
		message_id: str,
		status: str = "delivered",
		timestamp: int | str | None = None,
		errors: list[dict[str, Any]] | None = None,
	) -> dict[str, Any]:
		"""Generate Meta message lifecycle status update webhook (sent, delivered, read, failed)."""
		ts = str(timestamp or int(time.time()))
		clean_recipient = re.sub(r"\D", "", recipient_wa_id)

		status_obj: dict[str, Any] = {
			"id": message_id,
			"status": str(status).lower(),
			"timestamp": ts,
			"recipient_id": clean_recipient,
			"conversation": {
				"id": f"conv_{uuid.uuid4().hex[:12]}",
				"origin": {"type": "marketing"},
			},
			"pricing": {
				"billable": True,
				"pricing_model": "CBP",
				"category": "marketing",
			},
		}
		if errors:
			status_obj["errors"] = errors

		return {
			"object": "whatsapp_business_account",
			"entry": [
				{
					"id": "WBA_100200",
					"changes": [
						{
							"field": "messages",
							"value": {
								"messaging_product": "whatsapp",
								"metadata": {
									"display_phone_number": "15551234567",
									"phone_number_id": str(phone_number_id),
								},
								"statuses": [status_obj],
							},
						}
					],
				}
			],
		}
