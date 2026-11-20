"""Shared page bounds for list APIs.

Whitelist arguments arrive as strings. These helpers keep every list endpoint
on a small, explicit page instead of an unbounded ``get_list``.
"""

from __future__ import annotations


def page_start(value) -> int:
	try:
		start = int(value or 0)
	except (TypeError, ValueError):
		start = 0
	return max(start, 0)


def page_limit(value, default: int = 40, maximum: int = 50) -> int:
	if value in (None, ""):
		limit = default
	else:
		try:
			limit = int(value)
		except (TypeError, ValueError):
			limit = default
	if limit < 1:
		limit = default
	return min(limit, maximum)
