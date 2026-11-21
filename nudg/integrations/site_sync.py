# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Copy WA Message rows to a client site.

A message that could not be written there stays the same WA Message, with
Client Sync set to Pending. When the site answers, those rows are pushed and
marked Synced.
"""

from __future__ import annotations

import frappe

from nudg.integrations.erpnext.client import ERPNextClientError

ATTEMPTS = 3
_DOWN_TTL = 60
_SYNC_FIELD = "client_sync"


def call_with_retry(fn, attempts: int = ATTEMPTS):
	"""Return ``(result, error)``. A failed push is tried ``attempts`` times."""
	last = None
	for _ in range(max(int(attempts or 1), 1)):
		try:
			return fn(), None
		except ERPNextClientError as exc:
			last = exc
	return None, last


def is_site_down(exc: ERPNextClientError | None, *, down_on_not_found: bool = False) -> bool:
	"""True when the site, the API, or a missing WhatsApp DocType blocked the push."""
	if exc is None:
		return False
	if exc.retryable or exc.status_code in (401, 403, 408, 429, 500, 502, 503, 504, 530):
		return True
	text = str(exc).lower()
	if "could not reach" in text or "did not respond" in text or "refused the api" in text:
		return True
	if "cloudflare" in text and ("tunnel" in text or "1033" in text or "530" in text):
		return True
	if down_on_not_found and (exc.status_code == 404 or "not found" in text):
		return True
	return False


def mark_site_unreachable(account: str, message: str) -> None:
	if not account:
		return
	try:
		status = frappe.db.get_value("WA Account", account, "erp_status")
	except Exception:
		return
	if status == "Disabled":
		return
	try:
		frappe.db.set_value(
			"WA Account",
			account,
			{
				"erp_status": "Error",
				"erp_last_error": (message or "The ERPNext site could not be reached.")[:1000],
			},
			update_modified=False,
		)
	except Exception:
		frappe.log_error(title="Nudg site status")
		return
	try:
		frappe.cache().set_value(_down_key(account), "1", expires_in_sec=_DOWN_TTL)
	except Exception:
		pass


def mark_site_reachable(account: str) -> None:
	if not account:
		return
	try:
		status = frappe.db.get_value("WA Account", account, "erp_status")
	except Exception:
		return
	if status != "Error":
		_clear_down(account)
		return
	try:
		frappe.db.set_value(
			"WA Account",
			account,
			{"erp_status": "Connected", "erp_last_error": ""},
			update_modified=False,
		)
	except Exception:
		frappe.log_error(title="Nudg site status")
		return
	_clear_down(account)


def recently_unreachable(account: str) -> bool:
	try:
		return bool(frappe.cache().get_value(_down_key(account)))
	except Exception:
		return False


def site_responds(account: str) -> bool:
	"""True when the client site accepts the stored API key. Updates site status."""
	from nudg.integrations.erpnext.service import _client_for_site, _load_site

	try:
		site = _load_site(account)
	except Exception:
		return False
	if site is None or site.status == "Disabled" or not (site.site_url or "").strip():
		return False
	client = _client_for_site(site)
	if client is None:
		mark_site_unreachable(account, "Could not sign in to the ERPNext site.")
		return False
	try:
		client.get_logged_user()
	except ERPNextClientError as exc:
		mark_site_unreachable(account, str(exc))
		return False
	except Exception:
		mark_site_unreachable(account, "The ERPNext site could not be reached.")
		return False
	mark_site_reachable(account)
	return True


def has_sync_field() -> bool:
	try:
		return bool(frappe.db.has_column("WA Message", _SYNC_FIELD))
	except Exception:
		return False


def flag_message_for_client(doc, method=None) -> None:
	"""Mark a WA Message that was stored here while its client site was down."""
	try:
		if getattr(getattr(doc, "flags", None), "nudg_skip_client_sync", False):
			return
		if (doc.get(_SYNC_FIELD) or "") in ("Pending", "Synced", "Error"):
			return
		account = (doc.get("whatsapp_account") or "").strip()
		if not account or not (doc.get("message_id") or "").strip():
			return
		if frappe.db.get_value("WA Account", account, "erp_status") != "Error":
			return
		if not (frappe.db.get_value("WA Account", account, "erp_site_url") or "").strip():
			return
		if not doc.get("name") or not has_sync_field():
			return
		_set_sync(doc.name, "Pending", "")
	except Exception:
		frappe.log_error(title="Nudg client sync")


def remember_message(
	account: str,
	phone: str,
	profile_name: str,
	direction: str,
	message_id: str,
	*,
	message: str | None = None,
	status: str | None = None,
	error: str = "",
	pending: bool = True,
	timestamp: str | None = None,
	context_message_id: str | None = None,
	reaction: str | None = None,
) -> str | None:
	"""Keep one WA Message and set Client Sync so it can be pushed later."""
	if not account or not message_id:
		return None
	sync = "Pending" if pending else "Error"
	try:
		name = frappe.db.get_value("WA Message", {"message_id": message_id}, "name")
	except Exception:
		return None
	if name:
		if has_sync_field():
			values = {_SYNC_FIELD: sync, "client_sync_error": (error or "")[:1000]}
			if status:
				values["status"] = status
			frappe.db.set_value("WA Message", name, values, update_modified=False)
		return str(name)
	if not phone:
		return None
	try:
		from nudg.integrations.whatsapp import adapter

		profile = adapter.ensure_local_profile(phone, account, profile_name=profile_name or None)
	except Exception:
		frappe.log_error(title="Nudg client sync")
		return None
	if not profile:
		return None
	doc = frappe.get_doc(
		{
			"doctype": "WA Message",
			"to": profile,
			"message": message or "",
			"whatsapp_account": account,
			"direction": direction or "Incoming",
			"status": status or "Sent",
			"message_id": message_id,
			"timestamp": timestamp,
			"context_message_id": context_message_id,
			"reaction": reaction,
			_SYNC_FIELD: sync,
			"client_sync_error": (error or "")[:1000],
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.nudg_skip_client_sync = True
	try:
		doc.insert(ignore_permissions=True)
		if direction == "Outgoing":
			frappe.db.set_value("WA Message", doc.name, "docstatus", 1, update_modified=False)
		return doc.name
	except Exception:
		frappe.log_error(title="Nudg client sync")
		return None


def flush_account(account: str) -> None:
	"""Push WA Message rows whose Client Sync is Pending. Stops when the site stops answering."""
	if not account or getattr(frappe.flags, "nudg_flushing_client", None):
		return
	if not has_sync_field():
		return
	try:
		rows = frappe.get_all(
			"WA Message",
			filters={"whatsapp_account": account, _SYNC_FIELD: "Pending"},
			fields=[
				"name",
				"message_id",
				"message",
				"direction",
				"status",
				"to",
				"timestamp",
				"context_message_id",
				"reaction",
			],
			order_by="creation asc",
			limit_page_length=100,
		)
	except Exception:
		frappe.log_error(title="Nudg client sync")
		return
	if not rows:
		return
	frappe.flags.nudg_flushing_client = account
	try:
		from nudg.integrations.site_store import RemoteStore

		store = RemoteStore.for_delivery(account)
		for row in rows:
			phone, profile_name = _profile_phone(row.get("to"))
			ok = False
			try:
				ok = bool(
					store.push_message(
						{
							"phone": phone,
							"profile_name": profile_name or phone,
							"direction": row.get("direction") or "Incoming",
							"message": row.get("message") or "",
							"message_id": row.get("message_id") or "",
							"status": row.get("status") or "Sent",
							"timestamp": str(row.get("timestamp") or ""),
							"context_message_id": row.get("context_message_id"),
							"reaction": row.get("reaction"),
						}
					)
				)
			except Exception:
				frappe.log_error(title="Nudg client sync")
			if ok:
				_set_sync(row.get("name"), "Synced", "")
				continue
			error = str(getattr(store, "last_push_error", "") or "The ERPNext site did not accept this message.")
			if getattr(store, "site_blocked", False):
				_set_sync(row.get("name"), "Pending", error)
				break
			_set_sync(row.get("name"), "Error", error)
	finally:
		frappe.flags.nudg_flushing_client = None


def sync_client_sites() -> None:
	"""Mark silent sites Error, and push pending WA Message rows once a site answers."""
	try:
		if not frappe.db.exists("DocType", "WA Account"):
			return
		if not frappe.db.has_column("WA Account", "erp_status"):
			return
		rows = frappe.get_all(
			"WA Account",
			filters={"erp_site_url": ["is", "set"], "erp_status": ["in", ["Connected", "Error"]]},
			pluck="name",
			limit_page_length=100,
		)
	except Exception:
		frappe.log_error(title="Nudg site check")
		return
	for account in rows or []:
		if not isinstance(account, str) or not account:
			continue
		try:
			if not site_responds(account):
				continue
			flush_account(account)
		except Exception:
			frappe.log_error(title=f"Nudg site sync {account}")


def _set_sync(name: str | None, sync: str, error: str) -> None:
	if not name or not has_sync_field():
		return
	frappe.db.set_value(
		"WA Message",
		name,
		{_SYNC_FIELD: sync, "client_sync_error": (error or "")[:1000]},
		update_modified=False,
	)


def _profile_phone(profile: str | None) -> tuple[str, str]:
	if not profile:
		return "", ""
	try:
		row = frappe.db.get_value("WA Profile", profile, ["phone_number", "profile_name"], as_dict=True)
	except Exception:
		return "", ""
	if not isinstance(row, dict):
		return "", ""
	return str(row.get("phone_number") or ""), str(row.get("profile_name") or "")


def _down_key(account: str) -> str:
	return f"nudg:site-down:{account}"


def _clear_down(account: str) -> None:
	try:
		frappe.cache().delete_value(_down_key(account))
	except Exception:
		pass
