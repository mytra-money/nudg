# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Pure formatting, window-calculation, and message-folding helpers for the inbox."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from nudg.utils.errors import format_error_message

WINDOW = timedelta(hours=24)


def _tag_parts(raw) -> list[str]:
	if isinstance(raw, (list, tuple)):
		return [str(part).strip() for part in raw if str(part).strip()]
	return [part.strip() for part in str(raw or "").split(",") if part.strip()]


def _assignment_people(assignment: dict | None) -> tuple[str | None, list[str]]:
	"""Primary assignee plus every open assignee. Unassigned conversations have neither."""
	assignment = assignment or {}
	status = assignment.get("assignment_status") or "Unassigned"
	raw = assignment.get("assignees")
	people: list[str] = []
	if isinstance(raw, list):
		for person in raw:
			if person and person not in people:
				people.append(person)
	single = assignment.get("assignee")
	if single and single not in people and status == "Assigned":
		people.append(single)
	if status != "Assigned":
		people = []
	primary = people[0] if people else None
	return primary, people


def _row_dicts(value) -> list | None:
	if isinstance(value, list):
		return value
	return None


def _looks_like_datetime(value) -> bool:
	if isinstance(value, (datetime, date)):
		return True
	if not isinstance(value, str):
		return False
	text = value.strip()
	return len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-"


def _iso(value) -> str | None:
	if not value:
		return None
	if isinstance(value, str):
		return get_datetime(value).isoformat()
	if hasattr(value, "isoformat"):
		return value.isoformat()
	return str(value)


def _clip(value: str | None, limit: int = 8000) -> str | None:
	if not value:
		return value
	text = str(value)
	if len(text) <= limit:
		return text
	return text[:limit] + "…"


def _stamp(row):
	if not isinstance(row, frappe._dict):
		row = frappe._dict(row)
	row.creation = _iso(row.creation)
	row.is_template = bool(row.get("is_template"))
	if row.get("error_message"):
		row.error_message = format_error_message(row.error_message)
	return row


def _window(last_incoming: str | None) -> dict:
	if not last_incoming:
		return {"status": "unopened", "expires_at": None, "last_incoming_at": None}
	opened = get_datetime(last_incoming)
	expires = opened + WINDOW
	status = "open" if expires > now_datetime() else "closed"
	return {"status": status, "expires_at": expires.isoformat(), "last_incoming_at": opened.isoformat()}


def _window_from_messages(messages: list) -> dict:
	last = None
	for row in messages:
		if row.get("direction") == "Incoming" and not row.get("reaction"):
			last = row.get("creation")
	return _window(last)


def _latest_activity(item: dict) -> str:
	"""Newest incoming or outgoing message. Chats with no message sort last."""
	preview = item.get("preview") or {}
	return str(preview.get("creation") or "")


def _fold(messages: list) -> list:
	ordered = sorted(
		messages,
		key=lambda row: (_iso(row.get("creation")) or "", row.get("name") or ""),
	)
	seen_ids: set[str] = set()
	deduped = []
	for row in ordered:
		message_id = row.get("message_id")
		if message_id:
			if message_id in seen_ids:
				continue
			seen_ids.add(message_id)
		deduped.append(row)
	ordered = deduped
	by_id = {row.get("message_id"): row for row in ordered if row.get("message_id")}
	by_name = {row.get("name"): row for row in ordered}
	reactions: dict[str, dict[str, str]] = {}
	visible = []
	for row in ordered:
		target = row.get("context_message_id") or ""
		if not target and row.get("reaction") and row.get("reply_to_message"):
			quoted = by_name.get(row.get("reply_to_message"))
			target = (quoted or {}).get("message_id") or ""
		if row.get("reaction") is None or not target:
			visible.append(row)
			continue
		bucket = reactions.setdefault(target, {})
		direction = row.get("direction") or "Outgoing"
		if row.get("reaction"):
			bucket[direction] = row.get("reaction")
		else:
			bucket.pop(direction, None)

	for row in visible:
		row["reactions"] = [
			{"emoji": emoji, "direction": direction}
			for direction, emoji in reactions.get(row.get("message_id") or "", {}).items()
		]
		quoted = None
		if row.get("reply_to_message"):
			quoted = by_name.get(row.get("reply_to_message"))
		elif row.get("context_message_id"):
			quoted = by_id.get(row.get("context_message_id"))
		if quoted and not quoted.get("reaction"):
			row["reply_to"] = quoted.get("name")
			row["reply_to_direction"] = quoted.get("direction")
			row["reply_message"] = quoted.get("template") or quoted.get("message") or quoted.get("file_name") or _("Attachment")
		row["is_template"] = bool(row.get("is_template"))
	return visible
