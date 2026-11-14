# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""HTTP calls from Nudge to a customer's ERPNext site."""

from __future__ import annotations

import re
from typing import Any, Callable

import requests

from nudg.integrations.erpnext.safety import SiteURLError, validate_site_url

_TOKEN_RE = re.compile(r"(token\s+)[^\s\"']+", re.IGNORECASE)
Transport = Callable[..., requests.Response]


class ERPNextClientError(Exception):
	def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
		super().__init__(message)
		self.status_code = status_code
		self.retryable = retryable


def redact(text: str | None, secrets: list[str] | None = None) -> str:
	if not text:
		return ""
	cleaned = _TOKEN_RE.sub(r"\1[REDACTED]", str(text))
	for secret in secrets or []:
		if secret and len(secret) > 4:
			cleaned = cleaned.replace(secret, "[REDACTED]")
	return cleaned[:300]


class ERPNextClient:
	"""Talk to one ERPNext site with its API key. Redirects are not followed."""

	def __init__(
		self,
		site_url: str,
		api_key: str,
		api_secret: str,
		*,
		allow_http: bool = False,
		timeout: tuple[float, float] = (5.0, 20.0),
		transport: Transport | None = None,
	):
		self.site_url = validate_site_url(site_url, allow_http=allow_http)
		self.allow_http = allow_http
		self.api_key = (api_key or "").strip()
		self.api_secret = api_secret or ""
		self._secrets = [self.api_key, self.api_secret]
		self.timeout = timeout
		self.transport = transport or requests.request
		if not self.api_key or not self.api_secret:
			raise ERPNextClientError("An API key and API secret are required.")

	def get_logged_user(self) -> str:
		response = self.request("GET", "/api/method/frappe.auth.get_logged_user")
		message = (response.get("message") if isinstance(response, dict) else None) or ""
		if not message:
			raise ERPNextClientError("ERPNext did not confirm the API user.")
		return str(message)

	def create_communication(self, *, reference_doctype: str, reference_name: str, subject: str, content: str, phone: str) -> None:
		self.request(
			"POST",
			"/api/resource/Communication",
			json={
				"doctype": "Communication",
				"communication_type": "Automated Message",
				"communication_medium": "Other",
				"sent_or_received": "Sent",
				"subject": subject[:140],
				"content": content[:1000],
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"phone_no": phone,
			},
		)

	def request(
		self,
		method: str,
		path: str,
		*,
		json: dict | None = None,
		params: dict | None = None,
		allow_404: bool = False,
	) -> Any:
		# Resolve again so a DNS change to a private address is not reused.
		self.site_url = validate_site_url(self.site_url, allow_http=self.allow_http)
		url = self.site_url + path
		headers = {
			"Authorization": f"token {self.api_key}:{self.api_secret}",
			"Accept": "application/json",
		}
		try:
			response = self.transport(
				method,
				url,
				headers=headers,
				json=json,
				params=params,
				timeout=self.timeout,
				allow_redirects=False,
			)
		except requests.RequestException as exc:
			from nudg.integrations.erpnext.payload import classify_transport_failure

			kind = classify_transport_failure(exc)
			raise ERPNextClientError(
				"Could not reach the ERPNext site.",
				retryable=kind == "retryable",
			) from exc
		if allow_404 and response.status_code == 404:
			return None
		if response.status_code >= 400:
			raise ERPNextClientError(
				redact(response.text, self._secrets) or f"ERPNext returned HTTP {response.status_code}.",
				status_code=response.status_code,
				retryable=response.status_code in {408, 429, 500, 502, 503, 504},
			)
		if not response.content:
			return {}
		try:
			return response.json()
		except ValueError as exc:
			raise ERPNextClientError("ERPNext returned a response that was not JSON.") from exc
