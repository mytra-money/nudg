# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Unified message repository providing dual-mode storage and status tracking."""

from __future__ import annotations

import datetime
import json
from typing import Any

import frappe
from frappe.utils import now_datetime


def _saved_message_name(doc: Any, message_id: str | None) -> str | None:
	"""Return the WA Message name if this delivery was already stored."""
	name = getattr(doc, "name", None)
	if isinstance(name, str) and name and frappe.db.exists("WA Message", name):
		return name
	if not message_id:
		return None
	existing = frappe.db.get_value("WA Message", {"message_id": message_id}, "name")
	return existing if isinstance(existing, str) and existing else None


class DeskMessageRepository:
	"""Repository handling message persistence, deduplication, and status transitions."""

	@classmethod
	def is_self_hosted(cls) -> bool:
		"""True if official frappe/whatsapp DocTypes are present."""
		return bool(frappe.db.exists("DocType", "WA Message"))

	@classmethod
	def is_duplicate_message(cls, message_id: str) -> bool:
		"""Check whether a message ID has already been persisted."""
		if not message_id:
			return False
		if not frappe.db.exists("DocType", "WA Message"):
			return False
		return bool(frappe.db.exists("WA Message", {"message_id": message_id}))

	@classmethod
	def resolve_wa_account(cls, channel_name: str | None) -> str | None:
		"""Safely resolve a valid WA Account docname for WA Message linking.

		Resolution Order:
		1. If channel_name itself is an existing WA Account, return channel_name.
		2. Check official WA Settings default_account.
		3. Fallback to any existing WA Account record.
		4. Fallback to channel_name.
		"""
		if not channel_name and not frappe.db.exists("DocType", "WA Account"):
			return channel_name

		if channel_name and frappe.db.exists("WA Account", channel_name):
			return channel_name

		if frappe.db.exists("DocType", "WA Settings"):
			default_acc = frappe.db.get_single_value("WA Settings", "default_account")
			if default_acc and frappe.db.exists("WA Account", default_acc):
				return default_acc

		if frappe.db.exists("DocType", "WA Account"):
			first_acc = frappe.db.get_value("WA Account", {}, "name")
			if first_acc:
				return first_acc

		return channel_name

	@classmethod
	def save_incoming_message(
		cls,
		channel_name: str,
		msg: dict[str, Any],
		contact_id: str,
		contact_name: str = "",
	) -> dict[str, Any]:
		"""Persist an incoming message into the active store and publish realtime event."""
		message_id = msg.get("id")
		msg_type = msg.get("type", "text")
		raw_ts = msg.get("timestamp")
		try:
			timestamp_val = (
				datetime.datetime.fromtimestamp(float(raw_ts))
				if raw_ts
				else now_datetime()
			)
		except (ValueError, TypeError, OverflowError, OSError):
			try:
				timestamp_val = now_datetime()
			except Exception:
				timestamp_val = datetime.datetime.now()

		content = ""
		context_id = msg.get("context", {}).get("id") if msg.get("context") else None
		reaction_emoji = None

		if msg_type == "text":
			content = msg.get("text", {}).get("body", "")
		elif msg_type == "button":
			content = msg.get("button", {}).get("text", "")
		elif msg_type == "interactive":
			interactive = msg.get("interactive", {})
			button_reply = interactive.get("button_reply", {})
			list_reply = interactive.get("list_reply", {})
			content = button_reply.get("title") or list_reply.get("title") or ""
		elif msg_type == "reaction":
			reaction_data = msg.get("reaction", {})
			reaction_emoji = reaction_data.get("emoji")
			content = reaction_emoji or ""
			context_id = reaction_data.get("message_id")
		elif msg_type == "order":
			order_data = msg.get("order", {})
			try:
				from nudg.services.catalog import parse_inbound_order
				parsed = parse_inbound_order(order_data)
				content = parsed.get("summary_text") or "Cart order"
			except Exception:
				items = order_data.get("product_items", [])
				content = f"Cart order ({len(items)} items)"
		elif msg_type in ("image", "video", "document"):
			media_data = msg.get(msg_type, {})
			content = media_data.get("caption") or ""

		media_fields: dict[str, Any] = {}
		if msg_type in ("image", "audio", "document", "video", "sticker"):
			media = msg.get(msg_type, {})
			media_fields = {
				"media_id": media.get("id"),
				"mime_type": media.get("mime_type"),
				"media_url": media.get("filename") if msg_type == "document" else "",
			}

		record_name = message_id or "msg_unidentified"

		if cls.is_self_hosted():
			wa_acc = cls.resolve_wa_account(channel_name)
			doc = frappe.get_doc({
				"doctype": "WA Message",
				"to": contact_id,
				"from": msg.get("from"),
				"message": content,
				"whatsapp_account": wa_acc,
				"direction": "Incoming",
				"status": "Sent",
				"message_id": message_id,
				"timestamp": timestamp_val,
				"reaction": reaction_emoji,
				"context_message_id": context_id,
				**media_fields,
			})
			doc.flags.ignore_permissions = True
			if not wa_acc:
				doc.flags.ignore_mandatory = True
				doc.flags.ignore_links = True
			try:
				doc.submit()
			except Exception:
				# submit() already inserts. A later error must not insert again:
				# a second insert clears the name and stores a duplicate message,
				# which runs the automation rule a second time.
				saved = _saved_message_name(doc, message_id)
				if saved:
					record_name = saved
				else:
					try:
						doc.insert()
					except Exception:
						existing = frappe.db.get_value("WA Message", {"message_id": message_id}, "name")
						record_name = existing if isinstance(existing, str) and existing else (message_id or "msg_unidentified")
					else:
						record_name = doc.name
			else:
				record_name = doc.name

		# Emit realtime broadcast to active browser sessions
		frappe.publish_realtime(
			"nudg_message",
			{
				"record_name": record_name,
				"message_id": message_id,
				"channel": channel_name,
				"contact": contact_id,
				"contact_name": contact_name,
				"content": content,
				"direction": "Incoming",
				"status": "Sent",
				"timestamp": str(timestamp_val),
			},
		)

		return {
			"record_name": record_name,
			"message_id": message_id,
			"content": content,
			"status": "Sent",
		}

	@classmethod
	def update_message_status(
		cls,
		message_id: str,
		new_status_raw: str,
		timestamp: str | int | None = None,
		errors: list[dict] | None = None,
	) -> bool:
		"""Update message lifecycle status (Sent -> Delivered -> Read / Failed)."""
		if not message_id:
			return False

		status_map = {
			"sent": "Sent",
			"delivered": "Delivered",
			"read": "Read",
			"failed": "Failed",
		}
		new_status = status_map.get(str(new_status_raw).lower(), "Sent")

		if not frappe.db.exists("DocType", "WA Message"):
			return False

		name = frappe.db.get_value("WA Message", {"message_id": message_id}, "name")
		if not name:
			return False

		current_status = frappe.db.get_value("WA Message", name, "status")
		# Precedence check: Read > Delivered > Sent. Never revert unless marking Failed.
		rank = {"Sent": 1, "Delivered": 2, "Read": 3, "Failed": 4}
		if current_status == "Failed" or (rank.get(current_status, 0) >= rank.get(new_status, 0) and new_status != "Failed"):
			return False

		updates: dict[str, Any] = {"status": new_status}
		if errors:
			updates["error_message"] = json.dumps(errors)

		frappe.db.set_value("WA Message", name, updates)

		frappe.publish_realtime(
			"nudg_message_status",
			{
				"message_id": message_id,
				"record_name": name,
				"status": new_status,
				"errors": errors or [],
			},
		)
		profile = frappe.db.get_value("WA Message", name, "to")
		try:
			from nudg.api import publish_inbox_change

			publish_inbox_change(profile, name, bump=False)
		except Exception:
			pass
		return True

	@classmethod
	def get_conversation_messages(
		cls,
		conversation_id: str,
		limit: int = 50,
		before: str | None = None,
	) -> list[dict[str, Any]]:
		"""Retrieve message history for a conversation or contact ID."""
		if cls.is_self_hosted():
			filters: dict[str, Any] = {"to": conversation_id}
			return frappe.get_all(
				"WA Message",
				filters=filters,
				fields=["name", "message_id", "message", "direction", "status", "timestamp", "creation"],
				order_by="creation desc",
				limit_page_length=limit,
			)
		return []
