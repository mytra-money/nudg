"""Conversation status for the inbox filter.

This is the single field the desk maintains for list filters. It is computed from
official WhatsApp records (``WA Profile.status``, latest ``WA Message``, and the
Meta 24-hour customer-service window). It is not a separate DocType.
"""

from __future__ import annotations

# Stable API values. Keep labels in the frontend / docs in sync with these.
BLOCKED = "blocked"
FAILED = "failed"
NEEDS_REPLY = "needs_reply"
WINDOW_OPEN = "window_open"
TEMPLATE_ONLY = "template_only"

ALL = (BLOCKED, FAILED, NEEDS_REPLY, WINDOW_OPEN, TEMPLATE_ONLY)


def conversation_status(profile: dict, preview: dict | None, window: dict) -> str:
	"""Return the primary inbox status for one conversation.

	Priority (first match wins):

	1. ``blocked`` — ``WA Profile.status`` is Blocked
	2. ``failed`` — latest non-reaction message has status Failed
	3. ``needs_reply`` — latest message is Incoming
	4. ``window_open`` — a customer message opened the 24-hour window and it is still open
	5. ``template_only`` — window closed or never opened (free-form send is not allowed)
	"""
	if (profile or {}).get("status") == "Blocked":
		return BLOCKED
	if preview and preview.get("status") == "Failed":
		return FAILED
	if preview and preview.get("direction") == "Incoming":
		return NEEDS_REPLY
	if (window or {}).get("status") == "open":
		return WINDOW_OPEN
	return TEMPLATE_ONLY
