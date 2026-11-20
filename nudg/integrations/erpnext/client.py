# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""HTTP calls from Nudge to a customer's ERPNext site."""

from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib.parse import quote

import requests

from nudg.integrations.erpnext.safety import SiteURLError, validate_site_url

_TOKEN_RE = re.compile(r"(token\s+)[^\s\"']+", re.IGNORECASE)
_BEARER_RE = re.compile(r"(bearer\s+)[^\s\"']+", re.IGNORECASE)
_SECRET_FIELD_RE = re.compile(
	r"(?i)(api[_-]?key|api[_-]?secret|access[_-]?token|authorization)([=:]\s*)([^\s\"']+)"
)
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
	cleaned = _BEARER_RE.sub(r"\1[REDACTED]", cleaned)
	cleaned = _SECRET_FIELD_RE.sub(r"\1\2[REDACTED]", cleaned)
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
		allow_loopback: bool = False,
		timeout: tuple[float, float] = (3.0, 10.0),
		transport: Transport | None = None,
	):
		self.site_url = validate_site_url(site_url, allow_http=allow_http, allow_loopback=allow_loopback)
		self.allow_http = allow_http
		self.allow_loopback = allow_loopback
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

	def get_resources(
		self,
		doctype: str,
		*,
		fields: list[str],
		filters: list | dict | None = None,
		limit: int = 100,
		order_by: str = "modified desc",
	) -> list:
		result = self._data(
			self.request(
				"GET",
				f"/api/resource/{quote(doctype, safe='')}",
				params={
					"fields": json.dumps(fields),
					"filters": json.dumps(filters or []),
					"limit_page_length": limit,
					"order_by": order_by,
				},
			)
		)
		return result if isinstance(result, list) else []

	def get_resource(self, doctype: str, name: str) -> dict | None:
		result = self._data(self.request("GET", self._resource_path(doctype, name), allow_404=True))
		return result if isinstance(result, dict) else None

	def insert_resource(self, doctype: str, doc: dict) -> dict:
		result = self._data(self.request("POST", f"/api/resource/{quote(doctype, safe='')}", json=doc))
		if not isinstance(result, dict):
			raise ERPNextClientError("ERPNext did not return the saved document.")
		return result

	def update_resource(self, doctype: str, name: str, doc: dict) -> dict:
		result = self._data(self.request("PUT", self._resource_path(doctype, name), json=doc))
		if not isinstance(result, dict):
			raise ERPNextClientError("ERPNext did not return the saved document.")
		return result

	def delete_resource(self, doctype: str, name: str) -> None:
		self.request("DELETE", self._resource_path(doctype, name))

	def call_method(self, method: str, payload: dict | None = None) -> Any:
		return self.request("POST", f"/api/method/{method}", json=payload or {})

	@staticmethod
	def _data(result: Any) -> Any:
		"""Frappe resource calls return the document under ``data``."""
		if isinstance(result, dict) and isinstance(result.get("data"), (dict, list)):
			return result["data"]
		return result

	@staticmethod
	def _resource_path(doctype: str, name: str) -> str:
		return f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}/"

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
		self.site_url = validate_site_url(
			self.site_url,
			allow_http=self.allow_http,
			allow_loopback=self.allow_loopback,
		)
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
		except requests.Timeout:
			raise ERPNextClientError(
				"The ERPNext site did not respond in time.",
				retryable=True,
			) from None
		except requests.ConnectionError:
			raise ERPNextClientError(
				"Could not reach the ERPNext site.",
				retryable=True,
			) from None
		except requests.RequestException as exc:
			from nudg.integrations.erpnext.payload import classify_transport_failure

			kind = classify_transport_failure(exc)
			raise ERPNextClientError(
				"Could not reach the ERPNext site.",
				retryable=kind == "retryable",
			) from None
		if allow_404 and response.status_code == 404:
			return None
		if response.status_code in {401, 403}:
			raise ERPNextClientError(
				"ERPNext refused the API credentials.",
				status_code=response.status_code,
				retryable=False,
			)
		if response.status_code >= 400:
			detail = redact(response.text, self._secrets)
			if response.status_code >= 500 and not detail:
				detail = "ERPNext could not complete the request."
			raise ERPNextClientError(
				detail or f"ERPNext returned HTTP {response.status_code}.",
				status_code=response.status_code,
				retryable=response.status_code in {408, 429, 500, 502, 503, 504},
			)
		if not response.content:
			return {}
		try:
			return response.json()
		except ValueError as exc:
			raise ERPNextClientError("ERPNext returned a response that was not JSON.") from exc
