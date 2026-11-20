# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Inbound WhatsApp message side effects.

A repeated webhook for the same message is rejected. The inbox is notified,
consent keywords are applied, and campaign delivery status is updated.
Replies are handled by the chatbot.
"""

from __future__ import annotations

import hashlib
from typing import Any

import frappe
from frappe import _


def on_wa_message(doc, method=None):
	"""Notify the inbox, apply consent keywords, and update campaign delivery."""
	if method in ("after_insert", "on_update"):
		try:
			from nudg.api import publish_inbox_change

			publish_inbox_change(doc.to, doc.name, bump=method == "after_insert" and not doc.get("reaction"))
		except Exception:
			pass

	if doc.get("reaction"):
		return

	if method == "after_insert":
		# Realtime broadcast for incoming messages
		if doc.direction == "Incoming":
			try:
				frappe.publish_realtime(
					"nudg_message",
					{
						"record_name": doc.name,
						"message_id": doc.message_id or doc.name,
						"channel": doc.whatsapp_account,
						"contact": doc.to,
						"content": doc.message or "",
						"direction": "Incoming",
						"status": doc.status or "Sent",
						"timestamp": str(doc.timestamp or doc.creation),
					},
					after_commit=True,
				)
			except Exception:
				pass

			# Check consent keywords
			try:
				from nudg.services import consent
				channel_doc = frappe.get_cached_doc("WA Account", doc.whatsapp_account) if doc.whatsapp_account else None
				consent.handle_incoming_consent(
					contact_id=doc.to,
					text=doc.message or "",
					channel_doc=channel_doc,
					phone_number=getattr(doc, "from", None),
					send_acknowledgment=True,
				)
			except Exception:
				pass

	elif method == "on_update":
		# Status update broadcast
		try:
			frappe.publish_realtime(
				"nudg_message_status",
				{
					"message_id": doc.message_id or doc.name,
					"record_name": doc.name,
					"status": doc.status,
				},
				after_commit=True,
			)
		except Exception:
			pass

		# Update campaign recipient status
		try:
			from nudg.services.campaigns import update_campaign_recipient_status
			raw_status = (doc.status or "").lower()
			update_campaign_recipient_status(doc.message_id or doc.name, raw_status, None)
		except Exception:
			pass

def guard_duplicate_inbound(doc, method=None):
	"""Ignore a second delivery of the same incoming WhatsApp message.

	Meta retries webhooks, and the desk webhook can overlap that retry. Both
	would otherwise insert a second WA Message for one customer message.
	"""
	if getattr(doc, "direction", None) != "Incoming":
		return
	message_id = (doc.get("message_id") or "").strip()
	if not message_id:
		return

	lock_name = _lock_name("wa-in", message_id)
	acquired = _acquire_db_lock(lock_name)
	try:
		existing = _message_name_for_id(message_id)
		if existing and existing != doc.get("name"):
			frappe.throw(
				_("This WhatsApp message was already received."),
				frappe.DuplicateEntryError,
			)
	except Exception:
		if acquired:
			_release_db_lock(lock_name)
		raise
	if acquired:
		_hold_lock_until_commit(lock_name)



def _message_name_for_id(message_id: str) -> str | None:
	try:
		row = frappe.db.sql(
			"SELECT name FROM `tabWA Message` WHERE message_id=%s LIMIT 1 FOR UPDATE",
			message_id,
		)
	except Exception:
		row = None
	found = _sql_name(row)
	if found:
		return found
	existing = frappe.db.get_value("WA Message", {"message_id": message_id}, "name")
	return existing if isinstance(existing, str) and existing else None


def _sql_name(row: Any) -> str | None:
	if not isinstance(row, (list, tuple)) or not row:
		return None
	cell = row[0]
	if isinstance(cell, dict):
		name = cell.get("name")
		return name if isinstance(name, str) and name else None
	if isinstance(cell, (list, tuple)) and cell and isinstance(cell[0], str) and cell[0]:
		return cell[0]
	return None


def _lock_name(prefix: str, key: str) -> str:
	digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
	return f"nudg:{prefix}:{digest}"[:64]


def _acquire_db_lock(name: str) -> bool:
	try:
		row = frappe.db.sql("SELECT GET_LOCK(%s, 15)", (name,))
	except Exception:
		return False
	if not isinstance(row, (list, tuple)) or not row:
		return False
	cell = row[0][0] if isinstance(row[0], (list, tuple)) and row[0] else None
	return cell == 1 or cell is True


def _release_db_lock(name: str) -> None:
	try:
		frappe.db.sql("SELECT RELEASE_LOCK(%s)", (name,))
	except Exception:
		pass


def _hold_lock_until_commit(name: str) -> None:
	def _release(lock_name: str = name) -> None:
		_release_db_lock(lock_name)

	after_commit = getattr(frappe.db, "after_commit", None)
	after_rollback = getattr(frappe.db, "after_rollback", None)
	if after_commit is not None and hasattr(after_commit, "add"):
		after_commit.add(_release)
		if after_rollback is not None and hasattr(after_rollback, "add"):
			after_rollback.add(_release)
		return
	_release()

