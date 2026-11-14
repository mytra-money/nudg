# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Reject ERPNext site URLs that point at the local machine or a private network."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlparse

Resolver = Callable[[str, int], list]

BLOCKED_HOSTS = frozenset(
	{
		"localhost",
		"localhost.localdomain",
		"metadata.google.internal",
		"metadata.google.com",
	}
)

MAX_URL_LENGTH = 300


class SiteURLError(ValueError):
	"""The ERPNext site URL is missing, unsafe, or not publicly reachable."""


def default_resolve(host: str, port: int) -> list:
	return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


def validate_site_url(
	url: str | None,
	*,
	allow_http: bool = False,
	resolve: Resolver = default_resolve,
) -> str:
	"""Return a canonical site origin, or raise SiteURLError.

	The hostname is resolved immediately. A URL is rejected when any answer is
	loopback, private, link-local, or otherwise not a public address. Callers
	check again before every outbound request.
	"""
	raw = (url or "").strip()
	if not raw or len(raw) > MAX_URL_LENGTH:
		raise SiteURLError("Enter the public HTTPS URL of the ERPNext site.")
	if any(char in raw for char in "\r\n\t {}"):
		raise SiteURLError("The site URL contains characters that are not allowed.")

	parsed = urlparse(raw)
	if parsed.username or parsed.password:
		raise SiteURLError("Put the API key in the credential fields, not in the URL.")
	if parsed.scheme == "http" and allow_http:
		pass
	elif parsed.scheme != "https":
		raise SiteURLError("The ERPNext site URL must start with https://.")
	host = (parsed.hostname or "").strip().lower().rstrip(".")
	if not host or host in BLOCKED_HOSTS or host.endswith(".local") or host.endswith(".internal"):
		raise SiteURLError("That host is not a public ERPNext site.")
	try:
		port = parsed.port
	except ValueError as exc:
		raise SiteURLError("The site URL has an invalid port.") from exc
	if port == 0:
		raise SiteURLError("The site URL has an invalid port.")
	if host.replace(".", "").isdigit() or ":" in host:
		_reject_ip(host)
	else:
		_reject_resolved(host, port or (443 if parsed.scheme == "https" else 80), resolve)

	path = (parsed.path or "").rstrip("/")
	origin = f"{parsed.scheme}://{host}"
	if port and port not in (80, 443):
		origin = f"{origin}:{port}"
	return origin + path


def _reject_resolved(host: str, port: int, resolve: Resolver) -> None:
	try:
		answers = resolve(host, port)
	except socket.gaierror as exc:
		raise SiteURLError("The ERPNext host could not be resolved.") from exc
	if not answers:
		raise SiteURLError("The ERPNext host could not be resolved.")
	for answer in answers:
		sockaddr = answer[4]
		ip = sockaddr[0]
		# IPv6 results may include a scope id after a percent sign.
		_reject_ip(ip.split("%", 1)[0])


def _reject_ip(value: str) -> None:
	try:
		addr = ipaddress.ip_address(value)
	except ValueError as exc:
		raise SiteURLError("The ERPNext host is not a valid address.") from exc
	if (
		addr.is_private
		or addr.is_loopback
		or addr.is_link_local
		or addr.is_multicast
		or addr.is_reserved
		or addr.is_unspecified
	):
		raise SiteURLError("The ERPNext host must be a public address.")
