# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Where a WhatsApp account keeps its chats.

A local account uses this site's database. A connected external site keeps the
same inbox and chatbot here, and stores WA Profile and WA Message on that site.
"""

from __future__ import annotations

import datetime
from typing import Any

import frappe
from frappe.utils import now_datetime

from nudg.integrations.erpnext.client import ERPNextClientError
from nudg.integrations.erpnext.service import _client_for_site, _load_site

_MESSAGE_FIELDS = [
	"name",
	"direction",
	"to",
	"from",
	"mime_type",
	"is_template",
	"media_url",
	"whatsapp_template",
	"message_id",
	"context_message_id",
	"reply_to_message",
	"creation",
	"message",
	"status",
	"reference_doctype",
	"reference_docname",
	"reaction",
	"error_code",
	"error_message",
	"whatsapp_account",
]

_STATUS = {"sent": "Sent", "delivered": "Delivered", "read": "Read", "failed": "Failed"}


def stores_remotely(account: str | None) -> bool:
	"""True when this account's chats are stored on its connected site."""
	return connected_site(account) is not None


def connected_site(account: str | None):
	"""The connected site for an account, or None when chats stay on this site."""
	if not isinstance(account, str) or not account:
		return None
	try:
		if not frappe.db.exists("DocType", "WA Account"):
			return None
		if not frappe.db.has_column("WA Account", "erp_status"):
			return None
		status = frappe.db.get_value("WA Account", account, "erp_status")
		url = frappe.db.get_value("WA Account", account, "erp_site_url")
	except Exception:
		return None
	if status != "Connected" or not isinstance(url, str) or not url.strip():
		return None
	try:
		site = _load_site(account)
	except Exception:
		return None
	if site is None or site.status != "Connected":
		return None
	return site


def payload_is_remote(payload: dict | None) -> bool:
	"""True when any message in this webhook belongs to a connected site."""
	try:
		if not isinstance(payload, dict):
			return False
		for entry in payload.get("entry") or []:
			if not isinstance(entry, dict):
				continue
			for change in entry.get("changes") or []:
				if not isinstance(change, dict):
					continue
				phone_id = ((change.get("value") or {}).get("metadata") or {}).get("phone_number_id")
				account = account_for_phone(phone_id)
				if account and stores_remotely(account):
					return True
	except Exception:
		return False
	return False


def account_for_phone(phone_number_id: str | None) -> str | None:
	if not phone_number_id:
		return None
	try:
		rows = frappe.get_all(
			"WA Account",
			filters={"phone_id": str(phone_number_id)},
			fields=["name", "erp_status"],
			limit_page_length=20,
		)
	except Exception:
		return None
	if not isinstance(rows, list) or not rows:
		return None
	for row in rows:
		if row.get("erp_status") == "Connected" and isinstance(row.get("name"), str):
			return row["name"]
	name = rows[0].get("name")
	return name if isinstance(name, str) and name else None


def ingest(payload: dict) -> None:
	"""Store a verified webhook. Connected accounts write to their site."""
	from nudg.integrations.whatsapp.adapter import apply_local_webhook

	for entry in payload.get("entry") or []:
		if not isinstance(entry, dict):
			continue
		for change in entry.get("changes") or []:
			if not isinstance(change, dict):
				continue
			field = change.get("field")
			value = change.get("value") or {}
			phone_id = (value.get("metadata") or {}).get("phone_number_id")
			account = account_for_phone(phone_id)
			if field == "messages" and account and stores_remotely(account):
				RemoteStore.for_account(account).take(value)
			else:
				apply_local_webhook(field, value)


@frappe.whitelist()
def send_message(
	to: str,
	message: str = "",
	attach: str | None = None,
	content_type: str = "text",
	reply_to: str | None = None,
	reference_doctype: str | None = None,
	reference_docname: str | None = None,
) -> str:
	"""Store a connected account's outgoing text on that account's site.

	A local account, and any message with a file, keeps the official send.
	That path still writes the official WhatsApp log.
	"""
	target = _desk_target(to)
	if target and stores_remotely(target["account"]) and not attach:
		name = send_text(target["phone"], target["account"], message or "") or ""
		_notify_outgoing(target["profile"], target["account"], message or "", name)
		return name
	from whatsapp.whatsapp.api.messages import send_message as official_send_message

	return official_send_message(
		to=to,
		message=message,
		attach=attach,
		content_type=content_type,
		reply_to=reply_to,
		reference_doctype=reference_doctype,
		reference_docname=reference_docname,
	)


@frappe.whitelist()
def send_template_message(
	template: str,
	to: str,
	reference_doctype: str | None = None,
	reference_docname: str | None = None,
) -> str:
	"""Store a connected account's template send on that account's site."""
	target = _desk_target(to)
	if target and stores_remotely(target["account"]):
		name = send_template(target["phone"], target["account"], template, None) or ""
		_notify_outgoing(target["profile"], target["account"], f"Template {template}", name)
		return name
	from whatsapp.whatsapp.api.messages import send_template as official_send_template

	return official_send_template(
		template=template,
		to=to,
		reference_doctype=reference_doctype,
		reference_docname=reference_docname,
	)


def _desk_target(to: str) -> dict | None:
	"""The local profile the inbox addressed, when it belongs to one account."""
	if not isinstance(to, str) or not to or not frappe.db.exists("WA Profile", to):
		return None
	row = frappe.db.get_value("WA Profile", to, ["name", "whatsapp_account", "phone_number"], as_dict=True)
	if not isinstance(row, dict):
		return None
	account = row.get("whatsapp_account")
	phone = row.get("phone_number")
	if not isinstance(account, str) or not isinstance(phone, str) or not phone:
		return None
	return {"profile": row.get("name"), "account": account, "phone": phone}


def _notify_outgoing(profile: str | None, account: str, message: str, name: str) -> None:
	if not profile or not name:
		return
	try:
		from nudg.api import publish_inbox_change

		publish_inbox_change(
			profile,
			bump=True,
			message=_present(
				{
					"name": name,
					"direction": "Outgoing",
					"message": message,
					"status": "Sent",
					"creation": _now(),
				},
				profile,
				account,
			),
		)
	except Exception:
		frappe.log_error(title="Remote inbox notify")


def send_text(phone: str, account: str, message: str) -> str | None:
	"""Send from this site's WhatsApp token and store the row on the connected site."""
	from nudg.integrations.whatsapp import adapter

	store = RemoteStore.for_account(account)
	profile = store.ensure_profile(phone, phone)
	message_id = adapter.deliver_text(account, phone, message)
	return store.save_outgoing(profile, message, message_id)


def send_buttons(phone: str, account: str, message: str, rows: list[dict]) -> str | None:
	from nudg.integrations.whatsapp import adapter

	store = RemoteStore.for_account(account)
	profile = store.ensure_profile(phone, phone)
	buttons = [{"id": row["button_id"], "title": row["title"]} for row in rows]
	message_id = adapter.deliver_buttons(account, phone, message, buttons)
	return store.save_outgoing(profile, message, message_id)


def send_template(phone: str, account: str, template: str, parameters: dict | None) -> str | None:
	from nudg.integrations.whatsapp import adapter

	store = RemoteStore.for_account(account)
	profile = store.ensure_profile(phone, phone)
	message_id = adapter.deliver_template(account, phone, template, parameters)
	label = f"Template {template}"
	return store.save_outgoing(profile, label, message_id)


def split_profiles(profile_names: list[str]) -> tuple[list[str], list[dict]]:
	"""Split inbox profiles into local names and connected-site rows."""
	if not profile_names:
		return [], []
	try:
		rows = frappe.get_all(
			"WA Profile",
			filters={"name": ["in", profile_names]},
			fields=["name", "whatsapp_account", "phone_number"],
			limit_page_length=max(len(profile_names), 1),
		)
	except Exception:
		return list(profile_names), []
	if not isinstance(rows, list):
		return list(profile_names), []
	remote: list[dict] = []
	remote_names: set[str] = set()
	for row in rows:
		name = row.get("name") if isinstance(row, dict) else getattr(row, "name", None)
		account = row.get("whatsapp_account") if isinstance(row, dict) else getattr(row, "whatsapp_account", None)
		phone = row.get("phone_number") if isinstance(row, dict) else getattr(row, "phone_number", None)
		if isinstance(name, str) and stores_remotely(account):
			remote.append({"name": name, "whatsapp_account": account, "phone_number": phone})
			remote_names.add(name)
	local = [name for name in profile_names if name not in remote_names]
	return local, remote


def thread_messages(profile: str, before: str | None, limit: int) -> list[dict] | None:
	"""Messages for a connected profile, newest last. None when the profile is local."""
	account, phone = _profile_account(profile)
	if not account or not stores_remotely(account):
		return None
	return RemoteStore.for_account(account).thread(profile, phone, before, limit)


def last_incoming_at(profile: str) -> str | None:
	"""Last incoming time, or '' when the connected thread has none. None when local."""
	account, phone = _profile_account(profile)
	if not account or not stores_remotely(account):
		return None
	return RemoteStore.for_account(account).last_incoming(phone) or ""


def _by_account(remote_profiles: list[dict]) -> dict[str, list[dict]]:
	grouped: dict[str, list[dict]] = {}
	for row in remote_profiles:
		account = row.get("whatsapp_account")
		if isinstance(account, str) and account:
			grouped.setdefault(account, []).append(row)
	return grouped


def previews(remote_profiles: list[dict]) -> dict[str, tuple[dict, str | None]]:
	"""Latest message and last incoming time, keyed by the local profile name."""
	found: dict[str, tuple[dict, str | None]] = {}
	for account, rows in _by_account(remote_profiles).items():
		try:
			found.update(RemoteStore.for_account(account).preview_map(rows))
		except Exception:
			frappe.log_error(title="Remote inbox preview")
	return found


def unread_counts(remote_profiles: list[dict]) -> dict[str, int]:
	counts: dict[str, int] = {}
	for account, rows in _by_account(remote_profiles).items():
		try:
			counts.update(RemoteStore.for_account(account).unread_map(rows))
		except Exception:
			frappe.log_error(title="Remote unread count")
			for row in rows:
				if row.get("name"):
					counts[row["name"]] = 0
	return counts


def history(phone: str, account: str, limit: int) -> list[dict] | None:
	"""Recent messages for the chatbot, oldest first. None when the account is local."""
	if not stores_remotely(account):
		return None
	return RemoteStore.for_account(account).history(phone, limit)


def mark_thread_read(profile: str) -> list[str] | None:
	"""Mark a connected thread read on their site.

	Returns the message ids that were unread, or None when the profile is stored locally.
	"""
	account, phone = _profile_account(profile)
	if not account or not stores_remotely(account):
		return None
	return RemoteStore.for_account(account).mark_read(phone, tell_meta=False, account=account)


def _profile_account(profile: str) -> tuple[str | None, str | None]:
	try:
		row = frappe.db.get_value("WA Profile", profile, ["whatsapp_account", "phone_number"], as_dict=True)
	except Exception:
		return None, None
	if not isinstance(row, dict):
		return None, None
	account = row.get("whatsapp_account")
	phone = row.get("phone_number")
	if not isinstance(account, str):
		return None, None
	return account, phone if isinstance(phone, str) else None


class RemoteStore:
	"""WA Profile and WA Message on one connected site."""

	def __init__(self, account: str, site, client):
		self.account = account
		self.site = site
		self.client = client
		self._remote_account: str | None = None

	@classmethod
	def for_account(cls, account: str) -> RemoteStore:
		cache = getattr(frappe.local, "nudg_remote_stores", None)
		if not isinstance(cache, dict):
			cache = {}
			frappe.local.nudg_remote_stores = cache
		cached = cache.get(account)
		if isinstance(cached, cls):
			return cached
		site = connected_site(account)
		if site is None:
			frappe.throw(f"WhatsApp account {account} is not connected to an external site.")
		client = _client_for_site(site)
		if client is None:
			frappe.throw(f"Could not sign in to the site connected on {account}.")
		store = cls(account, site, client)
		cache[account] = store
		return store

	def take(self, value: dict) -> None:
		contacts = value.get("contacts") or []
		contact_profile = contacts[0].get("profile") if contacts and isinstance(contacts[0], dict) else {}
		contact_name = (contact_profile or {}).get("name") or ""
		for msg in value.get("messages") or []:
			if isinstance(msg, dict):
				self._incoming(msg, contact_name)
		for status in value.get("statuses") or []:
			if isinstance(status, dict):
				self._status(status)

	def ensure_profile(self, phone: str, display_name: str | None = None) -> str:
		"""Return the WA Profile name on the connected site."""
		number = _display_phone(phone)
		remote_account = self.remote_account()
		found = self._first(
			"WA Profile",
			["name"],
			{"phone_number": number, "whatsapp_account": remote_account},
		)
		if found and found.get("name"):
			return str(found["name"])
		try:
			saved = self.client.insert_resource(
				"WA Profile",
				{
					"doctype": "WA Profile",
					"profile_name": display_name or number,
					"phone_number": number,
					"whatsapp_account": remote_account,
					"wa_id": _digits(phone),
					"status": "Active",
				},
			)
		except ERPNextClientError:
			found = self._first(
				"WA Profile",
				["name"],
				{"phone_number": number, "whatsapp_account": remote_account},
			)
			if found and found.get("name"):
				return str(found["name"])
			raise
		return str(saved.get("name") or "")

	def remote_account(self) -> str:
		if self._remote_account:
			return self._remote_account
		phone_id = frappe.db.get_value("WA Account", self.account, "phone_id")
		account_name = frappe.db.get_value("WA Account", self.account, "account_name") or self.account
		found = None
		if phone_id:
			found = self._first("WA Account", ["name"], {"phone_id": phone_id})
		if not found:
			found = self._first("WA Account", ["name"], {"account_name": account_name})
		if found and found.get("name"):
			self._remote_account = str(found["name"])
			return self._remote_account
		saved = self.client.insert_resource(
			"WA Account",
			{
				"doctype": "WA Account",
				"account_name": account_name,
				"status": "Active",
				"phone_id": phone_id or "",
			},
		)
		self._remote_account = str(saved.get("name") or account_name)
		return self._remote_account

	def save_outgoing(self, remote_profile: str, message: str, message_id: str) -> str:
		"""Record a message this site already sent. Their document is not submitted, so they do not send it again."""
		saved = self.client.insert_resource(
			"WA Message",
			{
				"doctype": "WA Message",
				"to": remote_profile,
				"message": message,
				"whatsapp_account": self.remote_account(),
				"direction": "Outgoing",
				"status": "Sent",
				"message_id": message_id,
				"timestamp": _now(),
			},
		)
		name = str(saved.get("name") or message_id)
		# Mark the row submitted without their before_submit, which would send it to Meta again.
		if saved.get("name"):
			try:
				self.client.call_method(
					"frappe.client.set_value",
					{"doctype": "WA Message", "name": name, "fieldname": "docstatus", "value": 1},
				)
			except ERPNextClientError:
				frappe.log_error(title="Remote outgoing submit flag")
		self._clear_error()
		return name

	def thread(self, local_profile: str, phone: str | None, before: str | None, limit: int) -> list[dict]:
		remote_profile = self._profile_name(phone) if phone else None
		if not remote_profile:
			return []
		filters: list = [["to", "=", remote_profile]]
		if before:
			filters.append(["creation", "<", before])
		rows = self.client.get_resources(
			"WA Message",
			fields=list(_MESSAGE_FIELDS),
			filters=filters,
			limit=limit,
			order_by="creation desc",
		)
		stamped = [_present(row, local_profile, self.account) for row in rows]
		return [row for row in stamped if row]

	def preview_map(self, rows: list[dict]) -> dict[str, tuple[dict, str | None]]:
		"""Latest message per local profile from one read of the connected site."""
		local_by_phone = {
			_display_phone(row.get("phone_number") or ""): row["name"]
			for row in rows
			if row.get("name") and row.get("phone_number")
		}
		if not local_by_phone:
			return {}
		snapshot = self._snapshot()
		remote_to_local = {}
		for profile in snapshot["profiles"]:
			local = local_by_phone.get(_display_phone(profile.get("phone_number") or ""))
			if local and profile.get("name"):
				remote_to_local[str(profile["name"])] = local
		found: dict[str, tuple[dict, str | None]] = {}
		incoming: dict[str, str] = {}
		for message in snapshot["messages"]:
			local = remote_to_local.get(str(message.get("to") or ""))
			if not local or message.get("reaction"):
				continue
			if local not in found:
				presented = _present(message, local, self.account)
				if presented:
					found[local] = (presented, None)
			if local not in incoming and message.get("direction") == "Incoming":
				created = message.get("creation")
				if created:
					incoming[local] = str(created)
		return {name: (preview, incoming.get(name)) for name, (preview, _incoming) in found.items()}

	def unread_map(self, rows: list[dict]) -> dict[str, int]:
		local_by_phone = {
			_display_phone(row.get("phone_number") or ""): row["name"]
			for row in rows
			if row.get("name") and row.get("phone_number")
		}
		if not local_by_phone:
			return {}
		snapshot = self._snapshot()
		remote_to_local = {}
		for profile in snapshot["profiles"]:
			local = local_by_phone.get(_display_phone(profile.get("phone_number") or ""))
			if local and profile.get("name"):
				remote_to_local[str(profile["name"])] = local
		counts = {row["name"]: 0 for row in rows if row.get("name")}
		for message in snapshot["unread"]:
			local = remote_to_local.get(str(message.get("to") or ""))
			if local and not message.get("reaction"):
				counts[local] = counts.get(local, 0) + 1
		return counts

	def _snapshot(self) -> dict:
		"""Profiles, recent messages, and unread rows for this connected account."""
		cached = getattr(self, "_inbox_snapshot", None)
		if isinstance(cached, dict):
			return cached
		remote_account = self.remote_account()
		profiles = self.client.get_resources(
			"WA Profile",
			fields=["name", "phone_number"],
			filters={"whatsapp_account": remote_account},
			limit=200,
		)
		messages = self.client.get_resources(
			"WA Message",
			fields=list(_MESSAGE_FIELDS),
			filters={"whatsapp_account": remote_account},
			limit=200,
			order_by="creation desc",
		)
		unread = self.client.get_resources(
			"WA Message",
			fields=["name", "to", "reaction", "status", "direction"],
			filters={
				"whatsapp_account": remote_account,
				"direction": "Incoming",
				"status": ["not in", ["Read", "Failed"]],
			},
			limit=200,
			order_by="creation desc",
		)
		self._inbox_snapshot = {"profiles": profiles, "messages": messages, "unread": unread}
		return self._inbox_snapshot

	def preview(self, local_profile: str, phone: str | None) -> tuple[dict | None, str | None]:
		preview = None
		incoming = None
		for row in self.thread(local_profile, phone, None, 20):
			if row.get("reaction"):
				continue
			if preview is None:
				preview = row
			if incoming is None and row.get("direction") == "Incoming":
				incoming = row.get("creation")
			if preview is not None and incoming is not None:
				break
		return preview, str(incoming) if incoming else None

	def last_incoming(self, phone: str | None) -> str | None:
		remote_profile = self._profile_name(phone) if phone else None
		if not remote_profile:
			return None
		rows = self.client.get_resources(
			"WA Message",
			fields=["creation", "direction", "reaction"],
			filters={"to": remote_profile, "direction": "Incoming"},
			limit=10,
			order_by="creation desc",
		)
		for row in rows:
			if row.get("reaction"):
				continue
			created = row.get("creation")
			return str(created) if created else None
		return None

	def unread(self, phone: str | None) -> int:
		remote_profile = self._profile_name(phone) if phone else None
		if not remote_profile:
			return 0
		return self._count(
			"WA Message",
			{"to": remote_profile, "direction": "Incoming", "status": ["not in", ["Read", "Failed"]]},
		)

	def history(self, phone: str, limit: int) -> list[dict]:
		rows = list(reversed(self.thread(phone, phone, None, limit)))
		history = []
		for row in rows:
			if row.get("reaction"):
				continue
			history.append({
				"direction": "Incoming" if row.get("direction") == "Incoming" else "Outgoing",
				"message": row.get("message") or "",
				"timestamp": row.get("creation"),
			})
		return history[-limit:]

	def mark_read(self, phone: str | None, tell_meta: bool, account: str) -> list[str]:
		from nudg.integrations.whatsapp import adapter

		remote_profile = self._profile_name(phone) if phone else None
		if not remote_profile:
			return []
		rows = self.client.get_resources(
			"WA Message",
			fields=["name", "message_id", "status", "reaction"],
			filters={"to": remote_profile, "direction": "Incoming", "status": ["not in", ["Read", "Failed"]]},
			limit=50,
			order_by="creation desc",
		)
		pending = [row for row in rows if row.get("name") and not row.get("reaction")]
		if not pending:
			return []
		import json

		self.client.call_method(
			"frappe.client.bulk_update",
			{
				"docs": json.dumps([
					{"doctype": "WA Message", "docname": row["name"], "status": "Read"}
					for row in pending
				])
			},
		)
		message_ids = [str(row["message_id"]) for row in pending if row.get("message_id")]
		if tell_meta:
			for message_id in message_ids:
				adapter.mark_as_read(message_id, account)
		return message_ids

	def _incoming(self, msg: dict, contact_name: str) -> None:
		message_id = msg.get("id")
		if not message_id:
			return
		if self._message_by_id(str(message_id)):
			return
		phone = str(msg.get("from") or "")
		parsed = _parse_message(msg)
		remote_profile = self.ensure_profile(phone, contact_name or phone)
		doc = {
			"doctype": "WA Message",
			"to": remote_profile,
			"from": msg.get("to") or "",
			"message": parsed["content"],
			"whatsapp_account": self.remote_account(),
			"direction": "Incoming",
			"status": "Sent",
			"message_id": message_id,
			"timestamp": _timestamp(msg.get("timestamp")),
			"context_message_id": parsed["context_id"],
			"reaction": parsed["reaction"],
		}
		doc.update(parsed["media"])
		saved = self.client.insert_resource("WA Message", doc)
		name = str(saved.get("name") or "")
		try:
			self.client.call_method("frappe.client.submit", {"doc": saved})
		except ERPNextClientError:
			frappe.log_error(title="Remote incoming message submit")
		self._clear_error()
		local_profile = self._mirror_profile(phone, contact_name)
		self._run_side_effects(local_profile, phone, parsed, name, str(message_id))

	def _status(self, status: dict) -> None:
		message_id = status.get("id")
		if not message_id:
			return
		current = self._message_by_id(str(message_id))
		if not current or not current.get("name"):
			self._status_on_nudg(status)
			return
		new_status = _STATUS.get(str(status.get("status") or "").lower(), "Pending")
		if current.get("status") == new_status:
			return
		values: dict[str, Any] = {"status": new_status}
		errors = status.get("errors")
		if errors:
			import json

			values["error_message"] = json.dumps(errors)
		_set_remote_values(self.client, str(current["name"]), values)

	def _message_by_id(self, message_id: str) -> dict | None:
		return self._first("WA Message", ["name", "status", "message_id"], {"message_id": message_id})

	def _profile_name(self, phone: str) -> str | None:
		number = _display_phone(phone)
		found = self._first(
			"WA Profile",
			["name"],
			{"phone_number": number, "whatsapp_account": self.remote_account()},
		)
		if found and found.get("name"):
			return str(found["name"])
		return None

	def _first(self, doctype: str, fields: list[str], filters: dict) -> dict | None:
		rows = self.client.get_resources(doctype, fields=fields, filters=filters, limit=1)
		return rows[0] if rows else None

	def _mirror_profile(self, phone: str, contact_name: str) -> str | None:
		"""The inbox addresses a conversation by a profile on this site."""
		from nudg.integrations.whatsapp import adapter

		local = adapter.ensure_local_profile(
			_display_phone(phone),
			self.account,
			profile_name=contact_name or None,
			wa_id=_digits(phone),
		)
		if local:
			try:
				frappe.db.set_value("WA Profile", local, "wa_id", _digits(phone), update_modified=True)
			except Exception:
				pass
		return local

	def _run_side_effects(self, local_profile: str | None, phone: str, parsed: dict, name: str, message_id: str) -> None:
		text = parsed["content"] or ""
		if local_profile:
			try:
				from nudg.services import consent

				matched, _status_name = consent.handle_incoming_consent(
					contact_id=local_profile,
					text=text,
					channel_doc=None,
					phone_number=phone,
					send_acknowledgment=False,
				)
				if matched:
					ack = (
						"You have successfully unsubscribed and will no longer receive messages. Reply START to resubscribe."
						if _status_name == "Opted-Out"
						else "You have successfully subscribed to receive messages. Reply STOP at any time to unsubscribe."
					)
					send_text(phone, self.account, ack)
			except Exception:
				frappe.log_error(title="Remote consent")
		kind = parsed["kind"]
		if kind in ("text", "button", "flow"):
			try:
				from nudg.chatbot.processor import ChatbotProcessor

				ChatbotProcessor({
					"name": name,
					"from": _display_phone(phone),
					"message": text,
					"content_type": kind,
					"whatsapp_account": self.account,
					"button_payload": parsed["button_payload"],
					"flow_response": parsed["flow_response"],
				}).process()
			except Exception:
				frappe.log_error(title="Remote chatbot")
		if local_profile:
			try:
				from nudg.api import publish_inbox_change

				publish_inbox_change(
					local_profile,
					bump=True,
					message=_present(
						{
							"name": name,
							"direction": "Incoming",
							"message": text,
							"message_id": message_id,
							"status": "Sent",
							"creation": _now(),
							"reaction": parsed["reaction"],
						},
						local_profile,
						self.account,
					),
				)
			except Exception:
				frappe.log_error(title="Remote inbox notify")

	def _count(self, doctype: str, filters: dict) -> int:
		try:
			result = self.client.call_method(
				"frappe.client.get_count",
				{"doctype": doctype, "filters": filters},
			)
		except Exception:
			return 0
		message = result.get("message") if isinstance(result, dict) else result
		try:
			return int(message or 0)
		except (TypeError, ValueError):
			return 0

	def _status_on_nudg(self, status: dict) -> None:
		"""Update a message that is still stored on Nudg. The official webhook writes its own log."""
		message_id = status.get("id")
		if not message_id:
			return
		name = frappe.db.get_value("WA Message", {"message_id": str(message_id)}, "name")
		if not name:
			return
		new_status = _STATUS.get(str(status.get("status") or "").lower(), "Pending")
		old_status = frappe.db.get_value("WA Message", name, "status")
		if old_status == new_status:
			return
		values: dict[str, Any] = {"status": new_status}
		errors = status.get("errors")
		if errors:
			import json

			values["error_message"] = json.dumps(errors)
		frappe.db.set_value("WA Message", name, values, update_modified=False)

	def _clear_error(self) -> None:
		try:
			frappe.db.set_value("WA Account", self.account, "erp_last_error", "", update_modified=False)
		except Exception:
			pass


def _set_remote_values(client, name: str, values: dict) -> None:
	"""Update a submitted WA Message. The resource API refuses that save."""
	try:
		client.call_method(
			"nudg.integrations.site_store.update_message_fields",
			{"name": name, "values": values},
		)
	except ERPNextClientError:
		client.call_method(
			"frappe.client.set_value",
			{"doctype": "WA Message", "name": name, "fieldname": values},
		)


@frappe.whitelist()
def update_message_fields(name: str, values: dict | str) -> None:
	"""Set delivery fields on a WA Message, including a submitted one."""
	if frappe.session.user in (None, "Guest"):
		frappe.throw("Log in to update a WhatsApp message.", frappe.PermissionError)
	if isinstance(values, str):
		import json

		values = json.loads(values)
	if not isinstance(values, dict) or not name:
		frappe.throw("A message and its new values are required.")
	allowed = {"status", "error_message", "error_code", "conversation_id"}
	updates = {field: values.get(field) for field in allowed if field in values}
	status = updates.get("status")
	if status is not None and status not in {"Pending", "Sent", "Delivered", "Read", "Failed"}:
		frappe.throw("That message status is not valid.")
	if not updates or not frappe.db.exists("WA Message", name):
		return
	frappe.db.set_value("WA Message", name, updates, update_modified=False)


def _present(row: dict | None, local_profile: str, account: str) -> dict | None:
	if not isinstance(row, dict):
		return None
	presented = {field: row.get(field) for field in _MESSAGE_FIELDS}
	presented["to"] = local_profile
	presented["whatsapp_account"] = account
	presented["creation"] = str(row.get("creation") or _now())
	presented["is_template"] = bool(row.get("is_template"))
	return presented


def _parse_message(msg: dict) -> dict:
	kind = msg.get("type") or "text"
	content = ""
	button_payload = None
	flow_response = None
	reaction = None
	context_id = (msg.get("context") or {}).get("id") if isinstance(msg.get("context"), dict) else None
	content_kind = "text"
	if kind == "text":
		content = (msg.get("text") or {}).get("body") or ""
	elif kind == "button":
		button = msg.get("button") or {}
		content = button.get("text") or ""
		button_payload = button.get("payload") or content
		content_kind = "button"
	elif kind == "interactive":
		interactive = msg.get("interactive") or {}
		interactive_type = interactive.get("type")
		if interactive_type == "button_reply":
			reply = interactive.get("button_reply") or {}
			content = reply.get("title") or ""
			button_payload = reply.get("id") or content
			content_kind = "button"
		elif interactive_type == "list_reply":
			reply = interactive.get("list_reply") or {}
			content = reply.get("title") or ""
			button_payload = reply.get("id") or content
			content_kind = "button"
		elif interactive_type == "nfm_reply":
			raw = (interactive.get("nfm_reply") or {}).get("response_json")
			content = raw if isinstance(raw, str) else ""
			flow_response = raw
			content_kind = "flow"
	elif kind == "reaction":
		reaction_data = msg.get("reaction") or {}
		reaction = reaction_data.get("emoji")
		content = reaction or ""
		context_id = reaction_data.get("message_id")
		content_kind = "reaction"
	media = {}
	if kind in ("image", "audio", "document", "video", "sticker"):
		body = msg.get(kind) or {}
		content = content or body.get("caption") or ""
		media = {"media_id": body.get("id"), "mime_type": body.get("mime_type")}
		if kind == "document":
			media["media_url"] = body.get("filename") or ""
		content_kind = "media"
	return {
		"content": content,
		"kind": content_kind,
		"button_payload": button_payload,
		"flow_response": flow_response,
		"reaction": reaction,
		"context_id": context_id,
		"media": media,
	}


def _display_phone(phone: str) -> str:
	digits = _digits(phone)
	if not digits:
		return str(phone or "")
	return phone if str(phone).startswith("+") else f"+{digits}"


def _digits(phone: str) -> str:
	return "".join(ch for ch in str(phone or "") if ch.isdigit())


def _timestamp(raw) -> str:
	if not raw:
		return _now()
	try:
		return datetime.datetime.fromtimestamp(int(raw)).strftime("%Y-%m-%d %H:%M:%S")
	except (TypeError, ValueError, OSError):
		return _now()


def _now() -> str:
	try:
		return now_datetime().strftime("%Y-%m-%d %H:%M:%S")
	except Exception:
		return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
