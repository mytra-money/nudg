# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Reject external site URLs that point at the local machine or a private network."""

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
NAT64_PREFIXES = (
	ipaddress.IPv6Network("64:ff9b::/96"),
	ipaddress.IPv6Network("64:ff9b:1::/48"),
)


class SiteURLError(ValueError):
	"""The external site URL is missing, unsafe, or not publicly reachable."""


def default_resolve(host: str, port: int) -> list:
	return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


def validate_site_url(
	url: str | None,
	*,
	allow_http: bool = False,
	allow_loopback: bool = False,
	resolve: Resolver = default_resolve,
) -> str:
	"""Return a canonical site origin, or raise SiteURLError.

	The hostname is resolved immediately. A URL is rejected when any answer is
	loopback, private, link-local, or otherwise not a public address. Callers
	check again before every outbound request.
	"""
	raw = (url or "").strip()
	if not raw or len(raw) > MAX_URL_LENGTH:
		raise SiteURLError("Enter the public HTTPS URL of the external site.")
	if any(char in raw for char in "\r\n\t {}"):
		raise SiteURLError("The site URL contains characters that are not allowed.")

	parsed = urlparse(raw)
	if parsed.username or parsed.password:
		raise SiteURLError("Put the API key in the credential fields, not in the URL.")
	if parsed.scheme == "http" and allow_http:
		pass
	elif parsed.scheme != "https":
		raise SiteURLError("The external site URL must start with https://.")
	host = (parsed.hostname or "").strip().lower().rstrip(".")
	loopback = allow_loopback and _is_loopback_name(host)
	if not host or host.endswith(".local") or host.endswith(".internal"):
		raise SiteURLError("That host is not a public external site.")
	if host in BLOCKED_HOSTS and not loopback:
		raise SiteURLError("That host is not a public external site.")
	try:
		port = parsed.port
	except ValueError as exc:
		raise SiteURLError("The site URL has an invalid port.") from exc
	if port == 0:
		raise SiteURLError("The site URL has an invalid port.")
	if loopback:
		pass
	elif host.replace(".", "").isdigit() or ":" in host:
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
		raise SiteURLError("The external host could not be resolved.") from exc
	if not answers:
		raise SiteURLError("The external host could not be resolved.")
	for answer in answers:
		sockaddr = answer[4]
		ip = sockaddr[0]
		# IPv6 results may include a scope id after a percent sign.
		_reject_ip(ip.split("%", 1)[0])


def _is_loopback_name(host: str) -> bool:
	if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
		return True
	try:
		return ipaddress.ip_address(host).is_loopback
	except ValueError:
		return False


def _reject_ip(value: str) -> None:
	try:
		addr = ipaddress.ip_address(value)
	except ValueError as exc:
		raise SiteURLError("The external host is not a valid address.") from exc

	# RFC 6052 & RFC 8215: IPv4-IPv6 translation (NAT64).
	# Python ipaddress marks 64:ff9b::/96 as is_reserved=True even when the embedded IPv4 is global.
	if isinstance(addr, ipaddress.IPv6Address):
		if any(addr in net for net in NAT64_PREFIXES):
			v4 = ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
			if not (
				v4.is_private
				or v4.is_loopback
				or v4.is_link_local
				or v4.is_multicast
				or v4.is_reserved
				or v4.is_unspecified
			):
				return
			raise SiteURLError("The external host must be a public address.")
		if addr.ipv4_mapped:
			v4 = addr.ipv4_mapped
			if not (
				v4.is_private
				or v4.is_loopback
				or v4.is_link_local
				or v4.is_multicast
				or v4.is_reserved
				or v4.is_unspecified
			):
				return
			raise SiteURLError("The external host must be a public address.")

	if (
		addr.is_private
		or addr.is_loopback
		or addr.is_link_local
		or addr.is_multicast
		or addr.is_reserved
		or addr.is_unspecified
	):
		raise SiteURLError("The external host must be a public address.")
