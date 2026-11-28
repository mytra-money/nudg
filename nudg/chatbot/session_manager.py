# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Active chatbot sessions and the hourly timeout sweep."""

from __future__ import annotations

from datetime import datetime, timedelta

import frappe


class SessionManager:
	def __init__(self, phone_number, whatsapp_account):
		self.phone_number = phone_number
		self.account = whatsapp_account
		self.timeout_minutes = self.get_timeout()

	def get_timeout(self) -> int:
		try:
			from nudg.services.chatbot import get_settings

			settings = get_settings(self.account)
			if settings:
				return int(settings.session_timeout_minutes or 30)
		except Exception:
			pass
		return 30

	def get_active_session(self):
		try:
			self.expire_old_sessions()
			name = frappe.db.get_value(
				"WA Chatbot Session",
				{"phone_number": self.phone_number, "whatsapp_account": self.account, "status": "Active"},
				"name",
			)
			return frappe.get_doc("WA Chatbot Session", name) if name else None
		except Exception:
			frappe.log_error(title="Chatbot session lookup failed")
			return None

	def expire_old_sessions(self):
		threshold = datetime.now() - timedelta(minutes=self.timeout_minutes)
		try:
			filters = {"status": "Active", "last_activity": ["<", threshold]}
			if self.account:
				filters["whatsapp_account"] = self.account
			expired = frappe.get_all(
				"WA Chatbot Session",
				filters=filters,
				pluck="name",
			)
		except Exception:
			return
		for name in expired:
			_timeout_session(name)

	def get_conversation_history(self, limit: int = 20) -> list[dict]:
		"""Recent text messages with this phone, oldest first, for the AI prompt."""
		try:
			from nudg.integrations.site_store import history

			remote = history(self.phone_number, self.account, limit)
			if remote is not None:
				return remote
		except Exception:
			frappe.log_error(title="Chatbot remote history lookup failed")
		try:
			profile_names = frappe.get_all(
				"WA Profile",
				filters={"phone_number": self.phone_number},
				pluck="name",
			) if frappe.db.exists("DocType", "WA Profile") else []
			filters = {"whatsapp_account": self.account} if self.account else {}
			or_filters = [["from", "=", self.phone_number]]
			if profile_names:
				or_filters.append(["to", "in", profile_names])
			else:
				or_filters.append(["to", "=", self.phone_number])
			rows = frappe.get_all(
				"WA Message",
				filters=filters,
				or_filters=or_filters,
				fields=["direction", "message", "creation"],
				order_by="creation desc",
				limit=limit,
			)
		except Exception:
			frappe.log_error(title="Chatbot history lookup failed")
			return []

		history = []
		for row in reversed(rows):
			direction = row.get("direction") if isinstance(row, dict) else row.direction
			message = row.get("message") if isinstance(row, dict) else row.message
			created = row.get("creation") if isinstance(row, dict) else row.creation
			history.append({
				"direction": "Incoming" if direction == "Incoming" else "Outgoing",
				"message": message or "",
				"timestamp": created,
			})
		return history


def _timeout_session(name: str) -> None:
	session = frappe.get_doc("WA Chatbot Session", name)
	session.status = "Timeout"
	session.completed_at = datetime.now()
	session.save(ignore_permissions=True)


def cleanup_expired_sessions():
	"""Hourly job. Marks stale Active sessions as Timeout and sends the flow message."""
	try:
		if not frappe.db.exists("DocType", "WA Chatbot"):
			return
		bots = frappe.get_all(
			"WA Chatbot",
			filters={"enabled": 1},
			fields=["whatsapp_account", "session_timeout_minutes"],
		)
		for bot in bots:
			minutes = int(bot.session_timeout_minutes or 30)
			threshold = datetime.now() - timedelta(minutes=minutes)
			expired = frappe.get_all(
				"WA Chatbot Session",
				filters={
					"status": "Active",
					"whatsapp_account": bot.whatsapp_account,
					"last_activity": ["<", threshold],
				},
				pluck="name",
			)
			for name in expired:
				try:
					_timeout_session(name)
				except Exception:
					frappe.log_error(title=f"Chatbot session timeout failed: {name}")
	except Exception:
		frappe.log_error(title="Chatbot session cleanup failed")
