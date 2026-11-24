"""Whitelisted APIs for Phase 2 product modules. Guests are rejected."""

from __future__ import annotations

import json

import frappe
from frappe import _

from nudg.services import (
	analytics,
	assignments,
	campaigns,
	catalog as catalog_service,
	quick_replies,
)


def _require_login():
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to open Nudg."), frappe.PermissionError)


def _require_manager():
	"""Broadcasts, catalogs, accounts, and team changes are manager work."""
	_require_login()
	user = frappe.session.user
	if user == "Administrator":
		return
	roles = frappe.get_roles(user) if hasattr(frappe, "get_roles") else []
	if not isinstance(roles, (list, tuple, set)):
		return
	if "WhatsApp Manager" in roles or "System Manager" in roles:
		return
	frappe.throw(_("Only a WhatsApp Manager can do this."), frappe.PermissionError)


def _require_system_manager():
	"""WA Settings is one row for the whole site. Only Administrator and System Manager may read or change it."""
	_require_login()
	user = frappe.session.user
	if user == "Administrator":
		return
	roles = frappe.get_roles(user) if hasattr(frappe, "get_roles") else []
	if isinstance(roles, (list, tuple, set)) and "System Manager" in roles:
		return
	frappe.throw(_("Only a System Manager can change site WhatsApp settings."), frappe.PermissionError)


@frappe.whitelist()
def list_catalogs(account: str | None = None, start: int | None = 0, limit: int | None = None) -> list:
	_require_manager()
	return catalog_service.list_catalogs(account, start=start, limit=limit)


@frappe.whitelist()
def list_catalog_items(
	catalog: str | None = None,
	status: str | None = "Active",
	start: int | None = 0,
	limit: int | None = None,
) -> list:
	_require_login()
	return catalog_service.list_items(catalog, status, start=start, limit=limit)


@frappe.whitelist()
def import_erpnext_items_to_catalog(catalog: str, item_group: str | None = None, limit: int = 50) -> dict:
	"""Optional helper for self-hosted instances with ERPNext to bulk-import items into WA Catalog."""
	_require_manager()
	if not frappe.db.exists("DocType", "Item"):
		frappe.throw(_("ERPNext Item DocType not found on this site. You can add catalog items manually."))

	if not frappe.db.exists("WA Catalog", catalog):
		frappe.throw(_("Catalog {0} does not exist.").format(catalog))

	filters = {"disabled": 0}
	if item_group:
		filters["item_group"] = item_group

	items = frappe.get_all(
		"Item",
		filters=filters,
		fields=["name", "item_name", "description", "image"],
		limit=limit,
	)

	imported = 0
	for it in items:
		if frappe.db.exists("WA Catalog Item", {"catalog": catalog, "sku": it.name}):
			continue
		price = 0
		currency = "INR"
		if frappe.db.exists("DocType", "Item Price"):
			try:
				p = frappe.db.get_value("Item Price", {"item_code": it.name, "selling": 1}, ["price_list_rate", "currency"], as_dict=True)
				if p:
					price = p.price_list_rate or 0
					currency = p.currency or "INR"
			except Exception:
				pass

		doc = frappe.get_doc({
			"doctype": "WA Catalog Item",
			"catalog": catalog,
			"item_name": it.item_name or it.name,
			"sku": it.name,
			"description": it.description,
			"price": price,
			"currency": currency,
			"image": it.image,
			"status": "Active",
			"erpnext_item": it.name,
		})
		doc.insert(ignore_permissions=True)
		imported += 1

	return {"imported": imported, "total_scanned": len(items)}


@frappe.whitelist()
def sync_catalog(catalog: str) -> dict:
	_require_manager()
	return catalog_service.request_sync(catalog)


def _catalog_send_problems(profile: str, catalog_doc, item_doc) -> list[str]:
	"""Reasons this catalog product cannot be sent. Same list for every SKU."""
	from nudg.api import get_window_state

	problems: list[str] = []
	window = get_window_state(profile)
	if window.get("status") != "open":
		problems.append(
			_(
				"The 24-hour customer service window is closed, so Meta will reject every catalog product in this chat. "
				"Only an incoming customer message opens the window. Photos and texts you send do not. "
				"Ask the customer to reply, or send an approved template first."
			)
		)

	catalog_id = str(getattr(catalog_doc, "meta_catalog_id", None) or "").strip()
	catalog_name = getattr(catalog_doc, "catalog_name", None) or getattr(catalog_doc, "name", None) or _("Catalog")
	if not catalog_id:
		problems.append(
			_(
				"Catalog '{0}' has no Meta Catalog ID. Set the numeric id from Meta Commerce Manager in Catalogs. "
				"Every product in this catalog is blocked for that reason."
			).format(catalog_name)
		)
	elif not catalog_id.isdigit():
		problems.append(
			_(
				"Catalog '{0}' has Meta Catalog ID '{1}', which is not a numeric Meta Commerce catalog id. "
				"Update it in Catalogs. Every product in this catalog is blocked for that reason."
			).format(catalog_name, catalog_id)
		)

	retailer_id = getattr(item_doc, "meta_retailer_id", None) or getattr(item_doc, "sku", None) or getattr(item_doc, "name", None)
	if not str(retailer_id or "").strip():
		problems.append(_("This product has no SKU or Meta retailer id, so it cannot be sent."))
	return problems


def _catalog_failure_text(exc: Exception) -> str:
	"""Keep the Meta or connector message. Do not collapse it to 'Error sending'."""
	import re

	raw = getattr(exc, "message", None) or str(exc) or ""
	text = re.sub(r"EAAB\w+", "EAAB[REDACTED]", str(raw)).strip()
	text = re.sub(r"<[^>]+>", " ", text)
	text = re.sub(r"\s+", " ", text).strip()
	if not text:
		return _("Catalog product could not be sent.")
	if len(text) > 500:
		text = text[:500].rstrip() + "…"
	return text


@frappe.whitelist()
def send_catalog_product(
	profile: str,
	item: str,
	body_text: str | None = None,
	footer_text: str | None = None,
) -> dict:
	"""Dispatch an interactive Single-Product Message (SPM) to a profile in chat."""
	_require_login()
	if not profile:
		frappe.throw(_("Profile is required."))
	if not item:
		frappe.throw(_("Catalog Item is required."))

	profile_doc = None
	if frappe.db.exists("WA Profile", profile):
		profile_doc = frappe.get_doc("WA Profile", profile)
	else:
		found = (
			frappe.db.get_value("WA Profile", {"phone_number": profile}, "name")
			or frappe.db.get_value("WA Profile", {"profile_name": profile}, "name")
		)
		if found:
			profile_doc = frappe.get_doc("WA Profile", found)

	if not profile_doc:
		frappe.throw(_("Profile '{0}' not found.").format(profile))

	if profile_doc.status == "Blocked":
		frappe.throw(_("This profile is blocked. Unblock it before sending."))

	item_doc = frappe.get_doc("WA Catalog Item", item)
	catalog_doc = frappe.get_doc("WA Catalog", item_doc.catalog)
	problems = _catalog_send_problems(profile_doc.name, catalog_doc, item_doc)
	if problems:
		frappe.throw("\n\n".join(str(problem) for problem in problems), title=_("Catalog product was not sent"))

	catalog_id = str(catalog_doc.meta_catalog_id or "").strip()
	retailer_id = item_doc.meta_retailer_id or item_doc.sku or item_doc.name
	recipient_phone = profile_doc.phone_number or profile_doc.name
	account_name = profile_doc.whatsapp_account or frappe.db.get_value("WA Account", {"is_default": 1}, "name")

	try:
		res = catalog_service.send_single_product(
			channel=account_name,
			to=recipient_phone,
			catalog_id=catalog_id,
			product_retailer_id=retailer_id,
			body_text=body_text or f"Check out {item_doc.item_name} - {item_doc.currency or 'USD'} {item_doc.price}",
			footer_text=footer_text or "",
		)
		msg_id = res.get("message_id") if isinstance(res, dict) else ""
	except Exception as exc:
		frappe.log_error(title="Failed to send catalog product", message=frappe.get_traceback())
		frappe.throw(_catalog_failure_text(exc), title=_("Catalog product was not sent"))

	# Record outbound WA Message so it appears in the conversation thread
	wa_msg = frappe.new_doc("WA Message")
	wa_msg.update({
		"to": profile_doc.name,
		"direction": "Outgoing",
		"status": "Sent",
		"whatsapp_account": account_name,
		"message": f"🛍️ {item_doc.item_name}\nPrice: {item_doc.currency or 'USD'} {item_doc.price}\nSKU: {retailer_id}",
		"message_id": msg_id,
	})
	wa_msg.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"success": True,
		"message_name": wa_msg.name,
		"message_id": msg_id,
		"item": item_doc.name,
		"item_name": item_doc.item_name,
	}


@frappe.whitelist()
def list_quick_replies(
	account: str | None = None,
	status: str | None = "Active",
	start: int | None = 0,
	limit: int | None = None,
) -> list:
	_require_login()
	return quick_replies.list_quick_replies(account, status, start=start, limit=limit)


@frappe.whitelist()
def use_quick_reply(name: str) -> dict:
	_require_login()
	return quick_replies.use_quick_reply(name)


@frappe.whitelist()
def list_assignable_users(txt: str | None = None) -> list:
	"""Assign-dialog options limited to the caller's WA Account team."""
	_require_login()
	needle = (txt or "").strip().lower()
	names = assignments.get_assignable_account_users()
	if not assignments.can_view_team_users():
		me = frappe.session.user
		names = [me] if me in names else []
	if not names:
		return []

	rows = frappe.get_all(
		"User",
		filters={"name": ["in", names], "enabled": 1, "user_type": "System User"},
		fields=["name", "full_name", "email"],
		order_by="full_name asc",
	)
	options = []
	for row in rows or []:
		value = row.name
		if not value or value == "Guest":
			continue
		label = row.full_name or value
		email = row.email or ""
		if email and email != label:
			description = email
		elif label != value:
			description = value
		else:
			description = ""
		if needle and needle not in value.lower() and needle not in str(label).lower() and needle not in description.lower():
			continue
		options.append({"value": value, "label": label, "description": description})
	return options


@frappe.whitelist()
def assign_conversation(profile: str, user: str) -> dict:
	_require_login()
	return assignments.assign_conversation(profile, user, source="Manual", enforce_visibility=True)


@frappe.whitelist()
def unassign_conversation(profile: str, user: str | None = None) -> dict:
	_require_login()
	return assignments.unassign_conversation(profile, user)


@frappe.whitelist()
def close_conversation(profile: str) -> dict:
	_require_login()
	return assignments.close_conversation(profile)


@frappe.whitelist()
def ensure_conversation(profile: str) -> dict:
	_require_login()
	name = assignments.ensure_conversation(profile)
	doc = frappe.get_doc("WA Profile", name)
	frappe.has_permission("WA Profile", "read", doc=doc, throw=True)
	return assignments._serialize(doc)


@frappe.whitelist()
def set_conversation_tags(profile: str, tags: Any = None) -> dict:
	"""Whitelisted API: Set tags on a conversation."""
	_require_login()
	return assignments.set_conversation_tags(profile, tags)


@frappe.whitelist()
def add_conversation_note(profile: str, note_text: str) -> dict:
	"""Save an internal note. It is stored as a Comment and is never sent on WhatsApp."""
	_require_login()
	return assignments.add_conversation_note(profile, note_text)


@frappe.whitelist()
def get_webhook_setup() -> dict:
	"""Callback path and the site verify token for Meta. Managers only."""
	_require_manager()
	token = ""
	if frappe.db.exists("DocType", "WA Settings"):
		token = frappe.db.get_single_value("WA Settings", "webhook_verify_token") or ""
	return {
		"callback_method": "whatsapp.whatsapp.webhook.handler",
		"verify_token": token,
	}


@frappe.whitelist()
def auto_assign_round_robin(profile: str) -> dict:
	"""Whitelisted API: Auto-route conversation using round-robin distribution."""
	_require_login()
	return assignments.auto_assign_round_robin(profile)


@frappe.whitelist()
def list_utm_campaigns(account: str | None = None, start: int | None = 0, limit: int | None = None) -> list:
	"""Campaigns. These hold the template schedule and do not send."""
	_require_manager()
	return campaigns.list_campaigns(account, start, limit)


@frappe.whitelist()
def get_utm_campaign(name: str) -> dict:
	_require_manager()
	return campaigns.get_campaign(name)


@frappe.whitelist()
def create_utm_campaign(
	name: str,
	campaign_description: str | None = None,
	whatsapp_account: str | None = None,
	whatsapp_template: str | None = None,
	schedules: str | list | None = None,
) -> dict:
	_require_manager()
	return campaigns.create_campaign(
		name,
		campaign_description,
		whatsapp_account,
		whatsapp_template=whatsapp_template,
		schedules=schedules,
	)


@frappe.whitelist()
def update_utm_campaign(
	name: str,
	campaign_name: str | None = None,
	campaign_description: str | None = None,
	whatsapp_account: str | None = None,
	whatsapp_template: str | None = None,
	schedules: str | list | None = None,
) -> dict:
	_require_manager()
	return campaigns.update_campaign(
		name,
		campaign_name,
		campaign_description,
		whatsapp_account,
		whatsapp_template=whatsapp_template,
		schedules=schedules,
	)


@frappe.whitelist()
def delete_utm_campaign(name: str) -> dict:
	_require_manager()
	return campaigns.delete_campaign(name)


@frappe.whitelist()
def create_whatsapp_schedule(
	campaign: str | None = None,
	recipient_type: str | None = None,
	recipient: str | None = None,
	start_date: str | None = None,
	trigger_time: str | None = None,
	stop_on_reply: int | str | bool | None = 0,
	schedule_for: str | None = None,
	whatsapp_template: str | None = None,
	whatsapp_account: str | None = None,
) -> dict:
	"""Schedule a campaign or one WhatsApp template for one audience."""
	_require_manager()
	from nudg.services.campaign_schedules import schedule_whatsapp_campaign

	return schedule_whatsapp_campaign(
		campaign,
		recipient_type=recipient_type,
		recipient=recipient,
		start_date=start_date,
		trigger_time=trigger_time,
		stop_on_reply=stop_on_reply,
		schedule_for=schedule_for,
		whatsapp_template=whatsapp_template,
		whatsapp_account=whatsapp_account,
	)


@frappe.whitelist()
def update_whatsapp_schedule(
	name: str,
	campaign: str | None = None,
	recipient_type: str | None = None,
	recipient: str | None = None,
	start_date: str | None = None,
	trigger_time: str | None = None,
	stop_on_reply: int | str | bool | None = None,
	schedule_for: str | None = None,
	whatsapp_template: str | None = None,
	whatsapp_account: str | None = None,
) -> dict:
	_require_manager()
	from nudg.services.campaign_schedules import update_whatsapp_schedule as _update

	return _update(
		name,
		campaign=campaign,
		recipient_type=recipient_type,
		recipient=recipient,
		start_date=start_date,
		trigger_time=trigger_time,
		stop_on_reply=stop_on_reply,
		schedule_for=schedule_for,
		whatsapp_template=whatsapp_template,
		whatsapp_account=whatsapp_account,
	)


@frappe.whitelist()
def list_bulk_results(account: str | None = None) -> list:
	_require_manager()
	from nudg.services.campaign_schedules import list_bulk_results as _results

	return _results(account)


@frappe.whitelist()
def list_campaigns(account: str | None = None, start: int | None = 0, limit: int | None = None) -> list:
	_require_manager()
	from nudg.services.campaign_schedules import list_whatsapp_campaigns

	return list_whatsapp_campaigns(account)


@frappe.whitelist()
def get_campaign(name: str) -> dict:
	_require_manager()
	from nudg.services.campaign_schedules import get_whatsapp_campaign

	return get_whatsapp_campaign(name)


@frappe.whitelist()
def run_campaign(name: str) -> dict:
	"""Create the bulk messages that are due for this WhatsApp Campaign."""
	_require_manager()
	return campaigns.enqueue_run(name)


@frappe.whitelist()
def list_recipient_lists(account: str | None = None) -> list:
	_require_manager()
	return campaigns.list_recipient_lists(account)


@frappe.whitelist()
def list_recipient_profiles(account: str | None = None) -> list:
	_require_manager()
	from nudg.services.campaign_schedules import list_recipient_profiles as _profiles

	return _profiles(account)


@frappe.whitelist()
def create_campaign(
	name: str,
	campaign_description: str | None = None,
	whatsapp_account: str | None = None,
	recipient_type: str | None = None,
	recipient: str | None = None,
	start_date: str | None = None,
	trigger_time: str | None = None,
	stop_on_reply: int | str | bool | None = 0,
	schedules: str | list | None = None,
) -> dict:
	"""Create a WhatsApp Campaign. It sends the bulk message, not the campaign."""
	_require_manager()
	from nudg.services.campaign_schedules import create_whatsapp_campaign

	return create_whatsapp_campaign(
		name,
		campaign_description,
		whatsapp_account,
		recipient_type=recipient_type,
		recipient=recipient,
		start_date=start_date,
		trigger_time=trigger_time,
		stop_on_reply=stop_on_reply,
		schedules=schedules,
	)


@frappe.whitelist()
def update_campaign(
	name: str,
	campaign_name: str | None = None,
	campaign_description: str | None = None,
	whatsapp_account: str | None = None,
	recipient_type: str | None = None,
	recipient: str | None = None,
	start_date: str | None = None,
	trigger_time: str | None = None,
	stop_on_reply: int | str | bool | None = None,
	schedules: str | list | None = None,
) -> dict:
	_require_manager()
	from nudg.services.campaign_schedules import update_whatsapp_campaign

	return update_whatsapp_campaign(
		name,
		campaign_name,
		campaign_description,
		whatsapp_account,
		recipient_type=recipient_type,
		recipient=recipient,
		start_date=start_date,
		trigger_time=trigger_time,
		stop_on_reply=stop_on_reply,
		schedules=schedules,
	)


@frappe.whitelist()
def delete_campaign(name: str) -> dict:
	"""Delete a WhatsApp Campaign that has not created a bulk message."""
	_require_manager()
	from nudg.services.campaign_schedules import delete_whatsapp_campaign

	return delete_whatsapp_campaign(name)


@frappe.whitelist()
def create_catalog(
	catalog_name: str,
	whatsapp_account: str | None = None,
	description: str | None = None,
	status: str | None = None,
) -> dict:
	_require_manager()
	return catalog_service.create_catalog(catalog_name, whatsapp_account, description, status)


@frappe.whitelist()
def update_catalog(
	name: str,
	catalog_name: str | None = None,
	whatsapp_account: str | None = None,
	description: str | None = None,
	status: str | None = None,
) -> dict:
	_require_manager()
	return catalog_service.update_catalog(name, catalog_name, whatsapp_account, description, status)


@frappe.whitelist()
def delete_catalog(name: str) -> dict:
	"""Delete a catalog and its items."""
	_require_manager()
	name = (name or "").strip()
	if not name or not frappe.db.exists("WA Catalog", name):
		frappe.throw(_("Catalog not found."))
	doc = frappe.get_doc("WA Catalog", name)
	if doc.whatsapp_account:
		_assert_account_access(doc.whatsapp_account)
	for item in frappe.get_all("WA Catalog Item", filters={"catalog": name}, pluck="name"):
		frappe.delete_doc("WA Catalog Item", item, ignore_permissions=True, force=True)
	frappe.delete_doc("WA Catalog", name, ignore_permissions=True, force=True)
	return {"name": name, "deleted": True}


@frappe.whitelist()
def create_catalog_item(
	catalog: str,
	item_name: str,
	sku: str | None = None,
	description: str | None = None,
	price: str | float | None = None,
	currency: str | None = None,
	status: str | None = None,
	image: str | None = None,
) -> dict:
	_require_manager()
	return catalog_service.create_catalog_item(catalog, item_name, sku, description, price, currency, status, image)


@frappe.whitelist()
def update_catalog_item(
	name: str,
	item_name: str | None = None,
	sku: str | None = None,
	description: str | None = None,
	price: str | float | None = None,
	currency: str | None = None,
	status: str | None = None,
	image: str | None = None,
) -> dict:
	_require_manager()
	return catalog_service.update_catalog_item(name, item_name, sku, description, price, currency, status, image)


@frappe.whitelist()
def delete_catalog_item(name: str) -> dict:
	_require_manager()
	name = (name or "").strip()
	if not name or not frappe.db.exists("WA Catalog Item", name):
		frappe.throw(_("Catalog item not found."))
	catalog, account = frappe.db.get_value("WA Catalog Item", name, ["catalog", "whatsapp_account"]) or (None, None)
	if not account and catalog:
		account = frappe.db.get_value("WA Catalog", catalog, "whatsapp_account")
	if account:
		_assert_account_access(account)
	frappe.delete_doc("WA Catalog Item", name, ignore_permissions=True, force=True)
	return {"name": name, "deleted": True}


@frappe.whitelist()
def get_analytics(account: str | None = None) -> dict:
	"""Live metrics for the WhatsApp accounts this user is allowed to see."""
	_require_login()
	latest = analytics.latest_snapshot(account)
	if not latest.get("has_accounts", True):
		return {"latest": None, "refreshing": None, "history": [], "has_accounts": False}
	return {
		"latest": latest,
		"refreshing": analytics.refreshing_snapshot(account),
		"history": analytics.list_snapshots(account, limit=20),
		"has_accounts": True,
	}


@frappe.whitelist()
def refresh_analytics(account: str | None = None) -> dict:
	_require_login()
	if analytics.resolve_accounts(account) is None:
		frappe.throw(
			_("Connect a WhatsApp account before opening analytics."),
			frappe.PermissionError,
		)
	return analytics.enqueue_refresh(account)


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# WA Account & Team Management APIs (Direct User Permission Scoping)
# -----------------------------------------------------------------------------

@frappe.whitelist()
def get_user_account_status() -> dict:
	"""Check if current user has any configured & permitted WA Accounts."""
	_require_login()
	from nudg.security import get_user_wa_accounts
	accounts = get_user_wa_accounts(frappe.session.user)
	return {
		"has_accounts": len(accounts) > 0,
		"accounts": accounts,
		"count": len(accounts),
	}


def _wa_account_fields() -> list[str]:
	fields = ["name", "account_name", "status", "phone_id", "business_id", "app_id", "auto_read_receipts"]
	if frappe.db.has_column("WA Account", "is_default"):
		fields.append("is_default")
	if frappe.db.has_column("WA Account", "embedded_signup"):
		fields.append("embedded_signup")
	return fields


@frappe.whitelist()
def list_user_accounts() -> list[dict]:
	"""Return WA Accounts the current user has permission to access."""
	_require_login()
	from nudg.security import get_user_wa_accounts
	accounts = get_user_wa_accounts(frappe.session.user)
	if not accounts:
		return []

	return frappe.get_all(
		"WA Account",
		filters={"name": ["in", accounts]},
		fields=_wa_account_fields(),
		order_by="account_name asc",
	)


@frappe.whitelist()
def create_whatsapp_account(
	account_name: str,
	phone_id: str,
	access_token: str,
	business_id: str | None = None,
	app_id: str | None = None,
	auto_read_receipts: int = 1,
) -> dict:
	"""Configure a WhatsApp Account and immediately grant User Permission to this user."""
	_require_manager()
	account_name = (account_name or "").strip()
	phone_id = (phone_id or "").strip()
	access_token = (access_token or "").strip()
	business_id = (business_id or "").strip()
	app_id = (app_id or "").strip()

	if not account_name:
		frappe.throw(_("Account name is required."))
	if not phone_id:
		frappe.throw(_("Phone Number ID is required."))
	if not access_token:
		frappe.throw(_("Access token is required."))

	if frappe.db.exists("WA Account", account_name):
		frappe.throw(_("A WhatsApp Account with name '{0}' already exists.").format(account_name))

	doc = frappe.get_doc({
		"doctype": "WA Account",
		"account_name": account_name,
		"phone_id": phone_id,
		"access_token": access_token,
		"business_id": business_id,
		"app_id": app_id,
		"status": "Active",
		"auto_read_receipts": 1 if auto_read_receipts else 0,
	})
	doc.insert(ignore_permissions=True)

	# Grant User Permission for this WA Account to the creator
	from nudg.security import ensure_account_user_permission
	ensure_account_user_permission(doc.name, frappe.session.user)

	# Ensure creator has WhatsApp Manager role
	if frappe.session.user != "Administrator":
		user_doc = frappe.get_doc("User", frappe.session.user)
		if not any(r.role in ("WhatsApp Manager", "System Manager") for r in user_doc.roles):
			user_doc.append("roles", {"role": "WhatsApp Manager"})
			user_doc.save(ignore_permissions=True)

	frappe.db.commit()

	return {
		"status": "success",
		"account": doc.name,
		"account_name": doc.account_name,
		"phone_id": doc.phone_id,
		"message": _("WhatsApp Account '{0}' configured successfully.").format(account_name),
	}


@frappe.whitelist()
def update_whatsapp_account(
	name: str,
	status: str | None = None,
	auto_read_receipts: int | None = None,
	phone_id: str | None = None,
	business_id: str | None = None,
	app_id: str | None = None,
	access_token: str | None = None,
	is_default: int | None = None,
) -> dict:
	"""Update a connected number from Nudg. A blank credential is left unchanged."""
	_require_manager()
	name = (name or "").strip()
	if not name or not frappe.db.exists("WA Account", name):
		frappe.throw(_("WhatsApp Account not found."))
	_assert_account_access(name)
	doc = frappe.get_doc("WA Account", name)
	if status in ("Active", "Inactive"):
		doc.status = status
	if auto_read_receipts is not None:
		doc.auto_read_receipts = 1 if int(auto_read_receipts) else 0
	if phone_id and str(phone_id).strip():
		doc.phone_id = str(phone_id).strip()
	if business_id and str(business_id).strip():
		doc.business_id = str(business_id).strip()
	if app_id and str(app_id).strip():
		doc.app_id = str(app_id).strip()
	token = (access_token or "").strip()
	if token:
		doc.access_token = token
	doc.save(ignore_permissions=True)
	if is_default is not None:
		from nudg.security import set_account_default

		set_account_default(doc.name, int(is_default))
	marked = 0
	if frappe.db.has_column("WA Account", "is_default"):
		marked = 1 if frappe.db.get_value("WA Account", doc.name, "is_default") else 0
	return {
		"name": doc.name,
		"account_name": doc.account_name,
		"status": doc.status,
		"phone_id": doc.phone_id,
		"business_id": doc.business_id,
		"app_id": doc.app_id,
		"auto_read_receipts": doc.auto_read_receipts,
		"is_default": marked,
	}


@frappe.whitelist()
def get_whatsapp_settings() -> dict:
	"""Site WA Settings. The webhook secret is never returned. System Manager only."""
	_require_system_manager()
	if not frappe.db.exists("DocType", "WA Settings"):
		return {"callback_method": "whatsapp.whatsapp.webhook.handler"}
	doc = frappe.get_single("WA Settings")
	return {
		"default_account": doc.default_account or "",
		"whatsapp_api_url": doc.whatsapp_api_url or "",
		"whatsapp_api_version": doc.whatsapp_api_version or "",
		"webhook_verify_token": doc.webhook_verify_token or "",
		"has_webhook_secret": bool(doc.webhook_secret),
		"callback_method": "whatsapp.whatsapp.webhook.handler",
	}


@frappe.whitelist()
def save_whatsapp_settings(
	default_account: str | None = None,
	whatsapp_api_url: str | None = None,
	whatsapp_api_version: str | None = None,
	webhook_verify_token: str | None = None,
	webhook_secret: str | None = None,
) -> dict:
	"""Save site WhatsApp settings from Nudg. An empty secret keeps the current one."""
	_require_system_manager()
	if not frappe.db.exists("DocType", "WA Settings"):
		frappe.throw(_("WhatsApp Settings is not installed."))
	account = (default_account or "").strip()
	if account:
		_assert_account_access(account)
	doc = frappe.get_single("WA Settings")
	if default_account is not None:
		doc.default_account = account or None
	if whatsapp_api_url is not None:
		doc.whatsapp_api_url = (whatsapp_api_url or "").strip() or "https://graph.facebook.com"
	if whatsapp_api_version is not None:
		doc.whatsapp_api_version = (whatsapp_api_version or "").strip() or "v23.0"
	if webhook_verify_token is not None:
		doc.webhook_verify_token = (webhook_verify_token or "").strip()
	secret = (webhook_secret or "").strip()
	if secret:
		doc.webhook_secret = secret
	doc.save(ignore_permissions=True)
	return get_whatsapp_settings()


@frappe.whitelist()
def save_quick_reply(
	title: str,
	body: str,
	shortcut: str | None = None,
	whatsapp_account: str | None = None,
	status: str | None = None,
	name: str | None = None,
) -> dict:
	"""Create or update a quick reply without Desk."""
	_require_manager()
	title = (title or "").strip()
	body = (body or "").strip()
	shortcut = (shortcut or "").strip().lstrip("/")
	account = (whatsapp_account or "").strip()
	if not title:
		frappe.throw(_("Title is required."))
	if not body:
		frappe.throw(_("Message body is required."))
	if account:
		_assert_account_access(account)
	target = (name or "").strip()
	if target and frappe.db.exists("WA Quick Reply", target):
		doc = frappe.get_doc("WA Quick Reply", target)
		doc.shortcut = shortcut
		doc.body = body
		doc.whatsapp_account = account or None
		if status in ("Active", "Inactive"):
			doc.status = status
		doc.save(ignore_permissions=True)
		if title != doc.name:
			if frappe.db.exists("WA Quick Reply", title):
				frappe.throw(_("A quick reply named {0} already exists.").format(title))
			from frappe.model.rename_doc import rename_doc

			rename_doc("WA Quick Reply", doc.name, title, merge=False)
			doc = frappe.get_doc("WA Quick Reply", title)
	else:
		doc = frappe.new_doc("WA Quick Reply")
		doc.title = title
		doc.shortcut = shortcut
		doc.body = body
		doc.whatsapp_account = account or None
		doc.status = status if status in ("Active", "Inactive") else "Active"
		doc.insert(ignore_permissions=True)
	return {"name": doc.name, "title": doc.title, "shortcut": doc.shortcut, "status": doc.status}


@frappe.whitelist()
def delete_quick_reply(name: str) -> dict:
	_require_manager()
	name = (name or "").strip()
	if not name or not frappe.db.exists("WA Quick Reply", name):
		frappe.throw(_("Quick reply not found."))
	account = frappe.db.get_value("WA Quick Reply", name, "whatsapp_account")
	if account:
		_assert_account_access(account)
	frappe.delete_doc("WA Quick Reply", name, ignore_permissions=True, force=True)
	return {"name": name, "deleted": True}


@frappe.whitelist()
def save_whatsapp_template(
	template_label: str,
	message: str,
	whatsapp_account: str,
	template_type: str | None = None,
	language: str | None = None,
	footer: str | None = None,
	header_text: str | None = None,
	header_type: str | None = None,
	header_media: str | None = None,
	buttons: str | list | None = None,
	template_variables: str | list | None = None,
	name: str | None = None,
	submit_to_meta: int | str | bool | None = 1,
) -> dict:
	"""Create or update a WA Template.

	When ``submit_to_meta`` is truthy (default), the official WA Template save path
	pushes/updates on Meta. Pass ``0`` to keep a local draft without calling Meta.
	"""
	_require_manager()
	label = (template_label or "").strip()
	body = (message or "").strip()
	account = (whatsapp_account or "").strip()
	if not label:
		frappe.throw(_("Template label is required."))
	if not body:
		frappe.throw(_("Template message is required."))
	if not account or not frappe.db.exists("WA Account", account):
		frappe.throw(_("Choose a WhatsApp account."))
	_assert_account_access(account)
	kind = template_type if template_type in ("Utility", "Marketing", "Authentication") else "Marketing"
	publish = True
	if submit_to_meta is not None and str(submit_to_meta).strip() != "":
		publish = bool(frappe.utils.cint(submit_to_meta))
	target = (name or "").strip()
	if target and frappe.db.exists("WA Template", target):
		doc = frappe.get_doc("WA Template", target)
		if doc.whatsapp_account and doc.whatsapp_account != account:
			_assert_account_access(doc.whatsapp_account)
	else:
		doc = frappe.new_doc("WA Template")
	doc.language = _template_language(language or getattr(doc, "language", None))
	doc.template_label = label
	doc.message = body
	doc.template_type = kind
	doc.whatsapp_account = account
	doc.footer = (footer or "").strip()
	header_kinds = ("Text", "Image", "Document", "GIF", "Video")
	doc.header_type = header_type if header_type in header_kinds else (doc.header_type or "Text")
	doc.header_text = (header_text or "").strip()
	_apply_template_header_media(doc, header_media)
	_apply_template_buttons(doc, buttons)
	_apply_template_variables(doc, template_variables)
	# Meta stores template_name, not the label. WA Template derives the name in
	# validate(), but only when from_sync is unset. Draft saves set that flag
	# before insert so Meta is skipped, which also skips the derivation and
	# then validate throws "Template name is required".
	if not doc.whatsapp_template_id:
		_assign_local_template_name(doc, label)
	# WA Template.before_save skips Meta when from_sync is set (also used by Meta sync).
	if not publish:
		doc.flags.from_sync = True
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	_link_template_header_file(doc)
	return {
		"name": doc.name,
		"template_label": doc.template_label,
		"template_name": doc.template_name,
		"status": doc.status,
		"whatsapp_account": doc.whatsapp_account,
		"whatsapp_template_id": doc.whatsapp_template_id,
		"submitted_to_meta": publish,
	}


def _apply_template_header_media(doc, header_media: str | None) -> None:
	"""Store a local sample file. Text headers do not keep a file."""
	if doc.header_type == "Text":
		doc.header_media = None
		doc.header_media_handle = None
		doc.mime_type = None
		return
	media = (header_media or "").strip()
	if media and not (media.startswith("/files/") or media.startswith("/private/files/")):
		frappe.throw(_("Upload the sample from this page. A file address outside this site cannot be used."))
	if media != (doc.header_media or ""):
		doc.header_media_handle = None
		doc.mime_type = None
	doc.header_media = media or None
	doc.header_text = ""


def _link_template_header_file(doc) -> None:
	url = (doc.header_media or "").strip()
	if not url:
		return
	file_name = frappe.db.get_value("File", {"file_url": url}, "name")
	if not file_name:
		return
	frappe.db.set_value(
		"File",
		file_name,
		{
			"attached_to_doctype": "WA Template",
			"attached_to_name": doc.name,
			"attached_to_field": "header_media",
		},
		update_modified=False,
	)


def _assign_local_template_name(doc, label: str) -> None:
	"""Copy the label into Meta's template name before a local insert.

	Locked once the template has a Meta id. ``from_sync`` must not be set yet.
	"""
	import re

	from whatsapp.whatsapp.doctype.wa_template.wa_template import normalize_string

	derived = normalize_string(label)
	if not derived or not re.match(r"^[a-zA-Z0-9_]+$", derived):
		frappe.throw(
			_("Template label must use letters, numbers, or spaces. Meta stores it as the template name.")
		)
	doc.template_name = derived


def _apply_template_variables(doc, variables: str | list | None) -> None:
	"""Store the examples Meta reviews. Omitted payloads leave the child table alone."""
	if variables is None:
		return
	rows = variables
	if isinstance(variables, str):
		try:
			rows = json.loads(variables) if variables.strip() else []
		except (TypeError, ValueError):
			frappe.throw(_("Template variables must be a list."))
	if not isinstance(rows, list):
		frappe.throw(_("Template variables must be a list."))
	doc.set("template_variables", [])
	seen: set[str] = set()
	for row in rows:
		if not isinstance(row, dict):
			continue
		name = str(row.get("variable_name") or "").strip()
		if not name or name in seen:
			continue
		seen.add(name)
		doc.append(
			"template_variables",
			{
				"variable_name": name,
				"variable_example": str(row.get("variable_example") or "").strip(),
				"variable_field": str(row.get("variable_field") or "").strip(),
			},
		)


def _apply_template_buttons(doc, buttons: str | list | None) -> None:
	if buttons is None:
		return
	rows = buttons
	if isinstance(buttons, str):
		try:
			rows = json.loads(buttons) if buttons.strip() else []
		except (TypeError, ValueError):
			frappe.throw(_("Buttons must be a list."))
	if not isinstance(rows, list):
		frappe.throw(_("Buttons must be a list."))
	allowed = ("Quick Reply", "Copy Code", "URL", "Voice Call", "Phone Number")
	doc.set("buttons", [])
	for row in rows:
		if not isinstance(row, dict):
			continue
		text = (row.get("button_text") or "").strip()
		if not text:
			continue
		kind = row.get("button_type") if row.get("button_type") in allowed else "Quick Reply"
		doc.append(
			"buttons",
			{
				"button_type": kind,
				"button_text": text,
				"url": (row.get("url") or "").strip(),
				"phone_number": (row.get("phone_number") or "").strip(),
			},
		)


@frappe.whitelist()
def get_whatsapp_template(name: str) -> dict:
	_require_manager()
	name = (name or "").strip()
	if not name or not frappe.db.exists("WA Template", name):
		frappe.throw(_("Template not found."))
	doc = frappe.get_doc("WA Template", name)
	if doc.whatsapp_account:
		_assert_account_access(doc.whatsapp_account)
	return {
		"name": doc.name,
		"template_label": doc.template_label,
		"template_name": doc.template_name,
		"template_type": doc.template_type,
		"language": doc.language,
		"status": doc.status,
		"header_type": doc.header_type,
		"header_text": doc.header_text,
		"header_media": doc.header_media,
		"message": doc.message,
		"footer": doc.footer,
		"whatsapp_account": doc.whatsapp_account,
		"whatsapp_template_id": doc.whatsapp_template_id,
		"buttons": [
			{
				"button_type": row.button_type,
				"button_text": row.button_text,
				"url": row.url,
				"phone_number": row.phone_number,
			}
			for row in (doc.buttons or [])
		],
		"template_variables": [
			{
				"variable_name": row.variable_name,
				"variable_example": row.variable_example,
				"variable_field": row.variable_field,
			}
			for row in (doc.template_variables or [])
		],
	}


@frappe.whitelist()
def delete_whatsapp_template(name: str) -> dict:
	"""Remove the local template. Meta is unchanged until the next sync."""
	_require_manager()
	name = (name or "").strip()
	if not name or not frappe.db.exists("WA Template", name):
		frappe.throw(_("Template not found."))
	account = frappe.db.get_value("WA Template", name, "whatsapp_account")
	if account:
		_assert_account_access(account)
	frappe.delete_doc("WA Template", name, ignore_permissions=True, force=True)
	return {"name": name, "deleted": True}


@frappe.whitelist()
def sync_whatsapp_templates(account: str | None = None) -> dict:
	"""Pull templates from Meta for one account, or every account this manager can use."""
	_require_manager()
	from nudg.install import _apply_grants

	_apply_grants(
		{"WA Template": ("read", "write", "create", "report")},
		role_name="WhatsApp Manager",
		require_whatsapp=False,
	)
	frappe.clear_cache(doctype="WA Template")
	if hasattr(frappe.local, "role_permissions"):
		frappe.local.role_permissions = {}
	from whatsapp.whatsapp.doctype.wa_template.wa_template import sync_from_account

	target = (account or "").strip()
	if target:
		_assert_account_access(target)
		return sync_from_account(target)
	from nudg.security import get_user_wa_accounts

	names = get_user_wa_accounts(frappe.session.user) or []
	if not names:
		frappe.throw(_("No WhatsApp account is available to sync."))
	return {"accounts": [{"account": item, **(sync_from_account(item) or {})} for item in names]}


def _assert_account_access(account: str) -> None:
	from nudg.security import _get_roles, is_account_manager

	user = frappe.session.user
	if user == "Administrator" or "System Manager" in _get_roles(user):
		return
	if not is_account_manager(account, user):
		frappe.throw(_("You cannot change this WhatsApp account."), frappe.PermissionError)


def _template_language(requested: str | None) -> str:
	wanted = (requested or "en").strip() or "en"
	for candidate in (wanted, "en", "en_US"):
		if frappe.db.exists("WA Language", candidate):
			return candidate
	found = frappe.db.get_value("WA Language", {}, "name")
	if found:
		return found
	frappe.throw(_("No WhatsApp language is set up on this site."))


@frappe.whitelist()
def list_whatsapp_languages() -> list[dict]:
	"""Return WA Language rows for template editors (code + display name)."""
	if not frappe.db.exists("DocType", "WA Language"):
		return []
	rows = frappe.get_all(
		"WA Language",
		fields=["name", "language_code", "language_name"],
		order_by="language_name asc",
		limit_page_length=500,
	)
	out: list[dict] = []
	for row in rows:
		code = (row.get("language_code") or row.get("name") or "").strip()
		if not code:
			continue
		title = (row.get("language_name") or "").strip()
		out.append(
			{
				"value": code,
				"label": f"{title} — {code}" if title and title != code else code,
				"language_code": code,
				"language_name": title or code,
			}
		)
	return out


@frappe.whitelist()
def get_embedded_signup_config() -> dict:
	"""Public Embedded Signup values for the connect dialog. Never returns the app secret."""
	_require_manager()
	from nudg.integrations.embedded_signup import public_config

	return public_config()


@frappe.whitelist()
def save_embedded_signup_settings(
	app_id: str,
	config_id: str,
	app_secret: str | None = None,
	graph_api_version: str | None = None,
) -> dict:
	"""Store the Meta app id, Embedded Signup configuration id, and app secret."""
	_require_manager()
	from nudg.integrations.embedded_signup import save_settings

	return save_settings(app_id, config_id, app_secret, graph_api_version)


@frappe.whitelist()
def complete_embedded_signup(
	code: str,
	waba_id: str | None = None,
	phone_number_id: str | None = None,
	account_name: str | None = None,
	business_app: int | str | None = 0,
) -> dict:
	"""Exchange an Embedded Signup code and connect the customer's WhatsApp account."""
	_require_manager()
	from nudg.integrations.embedded_signup import complete_signup

	return complete_signup(code, waba_id, phone_number_id, account_name, business_app=business_app)


@frappe.whitelist()
def list_team_members(account: str | None = None) -> list:
	"""List team members who share the user's permitted WA Account(s)."""
	_require_login()
	user = frappe.session.user
	from nudg.security import get_user_wa_accounts, _get_roles
	user_accounts = get_user_wa_accounts(user)
	if not user_accounts:
		return []

	target_acc = account if (account and account in user_accounts) else user_accounts[0]

	user_perms = frappe.get_all(
		"User Permission",
		filters={"allow": "WA Account", "for_value": target_acc},
		pluck="user",
	)

	acc_owner = frappe.db.get_value("WA Account", target_acc, "owner")
	all_users = set(user_perms)
	if acc_owner:
		all_users.add(acc_owner)

	members = []
	for u in sorted(all_users):
		if not frappe.db.exists("User", u):
			continue
		udoc = frappe.get_value("User", u, ["name", "email", "first_name", "last_name", "full_name", "enabled", "user_image"], as_dict=True)
		roles = _get_roles(u)
		role_title = "WhatsApp Manager" if ("WhatsApp Manager" in roles or u == acc_owner or u == "Administrator") else "WhatsApp User"
		members.append({
			"email": udoc.email or udoc.name,
			"full_name": udoc.full_name or udoc.first_name or udoc.name,
			"role": role_title,
			"is_owner": u == acc_owner or u == "Administrator",
			"enabled": bool(udoc.enabled),
			"user_image": udoc.user_image or "",
			"account": target_acc,
		})
	return members


@frappe.whitelist()
def invite_team_members(
	emails: str,
	role: str = "WhatsApp Manager",
	account: str | None = None,
) -> dict:
	"""Invite teammates by email. They set their own password from the invitation.

	Same flow as Frappe CRM: a User Invitation, no password chosen by the manager.
	The WhatsApp number is granted when the invitation is accepted.
	"""
	_require_manager()
	account = (account or "").strip()
	if not account or not frappe.db.exists("WA Account", account):
		frappe.throw(_("Choose a WhatsApp account for this invitation."))
	_assert_account_access(account)
	target_role = "WhatsApp Manager" if role == "WhatsApp Manager" else "WhatsApp User"
	if not frappe.db.exists("DocType", "User Invitation"):
		frappe.throw(_("User invitations are not available on this site."))
	if not frappe.db.has_column("User Invitation", "nudg_account"):
		from nudg.install import setup_standard_custom_fields

		setup_standard_custom_fields()
	if not frappe.db.has_column("User Invitation", "nudg_account"):
		frappe.throw(_("Reload the site so team invitations can store the WhatsApp account."))
	from frappe.core.api.user_invitation import invite_by_email

	result = invite_by_email(
		emails,
		[target_role],
		"/nudg",
		app_name="nudg",
		nudg_account=account,
	)
	return result or {
		"disabled_user_emails": [],
		"accepted_invite_emails": [],
		"pending_invite_emails": [],
		"invited_emails": [],
	}


@frappe.whitelist()
def list_team_invitations(account: str | None = None) -> list:
	"""Pending Nudg invitations for numbers this manager can see."""
	_require_manager()
	if not frappe.db.exists("DocType", "User Invitation"):
		return []
	filters: dict = {"status": "Pending", "app_name": "nudg"}
	fields = ["name", "email", "creation"]
	if frappe.db.has_column("User Invitation", "nudg_account"):
		fields.append("nudg_account")
		if (account or "").strip():
			filters["nudg_account"] = account.strip()
	rows = frappe.get_all(
		"User Invitation",
		filters=filters,
		fields=fields,
		order_by="creation desc",
		limit_page_length=100,
	)
	from nudg.security import _get_roles, get_user_wa_accounts

	user = frappe.session.user
	see_all = user == "Administrator" or "System Manager" in _get_roles(user)
	allowed = set(get_user_wa_accounts(user))
	pending = []
	for row in rows or []:
		number = row.get("nudg_account") or ""
		if number and not see_all and number not in allowed:
			continue
		roles = frappe.get_all(
			"User Role",
			filters={"parent": row.name, "parenttype": "User Invitation"},
			pluck="role",
		)
		role = "WhatsApp Manager" if "WhatsApp Manager" in (roles or []) else "WhatsApp User"
		pending.append({
			"name": row.name,
			"email": row.email,
			"role": role,
			"account": number,
			"creation": row.creation,
		})
	return pending


def _invitation_for_manager(name: str):
	name = (name or "").strip()
	if not name or not frappe.db.exists("User Invitation", name):
		frappe.throw(_("Invitation not found."))
	invitation = frappe.get_doc("User Invitation", name)
	if invitation.app_name != "nudg":
		frappe.throw(_("Invitation not found."))
	account = (invitation.get("nudg_account") or "").strip()
	if account:
		_assert_account_access(account)
	return invitation


@frappe.whitelist()
def resend_team_invitation(name: str) -> dict:
	_require_manager()
	invitation = _invitation_for_manager(name)
	if invitation.status != "Pending":
		frappe.throw(_("Only a pending invitation can be resent."))
	invitation.send_invitation_mail()
	return {"status": "success", "email": invitation.email}


@frappe.whitelist()
def cancel_team_invitation(name: str) -> dict:
	_require_manager()
	invitation = _invitation_for_manager(name)
	if invitation.status != "Pending":
		frappe.throw(_("Only a pending invitation can be cancelled."))
	invitation.flags.ignore_permissions = True
	invitation.cancel_invite()
	return {"status": "success", "email": invitation.email}


@frappe.whitelist()
def update_team_member(
	account: str,
	email: str,
	role: str | None = None,
	enabled: int | None = None,
) -> dict:
	"""Update role or status of a team member. Passwords stay with the user."""
	_require_manager()
	user = frappe.session.user
	from nudg.security import is_account_manager, _get_roles

	if not is_account_manager(account, user) and "System Manager" not in _get_roles(user):
		frappe.throw(_("Only account managers can manage team members."), frappe.PermissionError)

	email = (email or "").strip().lower()
	if not frappe.db.exists("User", email):
		frappe.throw(_("User not found."))

	acc_owner = frappe.db.get_value("WA Account", account, "owner")
	if email == acc_owner and (enabled == 0 or role == "WhatsApp User"):
		frappe.throw(_("The primary account owner cannot be demoted or deactivated."))

	u = frappe.get_doc("User", email)

	if role in ("WhatsApp User", "WhatsApp Manager"):
		u.roles = [r for r in u.roles if r.role not in ("WhatsApp User", "WhatsApp Manager")]
		u.append("roles", {"role": role})
		if u.name not in ("Administrator", "Guest"):
			from nudg.desk_access import profile_name_for_roles

			profile = profile_name_for_roles({row.role for row in u.roles})
			if profile:
				u.module_profile = profile
			u.flags.nudg_profile_set = True

	if enabled is not None:
		u.enabled = 1 if enabled else 0

	u.save(ignore_permissions=True)

	return {
		"status": "success",
		"message": _("Team member updated successfully."),
		"email": email,
	}


def _chatbot_payload(payload):
	if isinstance(payload, str):
		payload = json.loads(payload or "{}")
	return payload if isinstance(payload, dict) else {}


@frappe.whitelist()
def get_chatbot(account: str) -> dict:
	_require_manager()
	_assert_account_access(account)
	from nudg.services.chatbot_setup import get_bot

	return get_bot(account)


@frappe.whitelist()
def save_chatbot(account: str, payload) -> dict:
	_require_manager()
	_assert_account_access(account)
	from nudg.services.chatbot_setup import save_bot

	return save_bot(account, _chatbot_payload(payload))


@frappe.whitelist()
def list_chatbot_keywords(account: str, start: int | None = 0, limit: int | None = None) -> list:
	_require_manager()
	_assert_account_access(account)
	from nudg.services.chatbot_setup import list_keywords

	return list_keywords(account, start=start, limit=limit)


@frappe.whitelist()
def save_chatbot_keyword(account: str, payload) -> dict:
	_require_manager()
	_assert_account_access(account)
	from nudg.services.chatbot_setup import save_keyword

	return save_keyword(account, _chatbot_payload(payload))


@frappe.whitelist()
def delete_chatbot_keyword(account: str, name: str) -> dict:
	_require_manager()
	_assert_account_access(account)
	from nudg.services.chatbot_setup import delete_keyword

	return delete_keyword(account, name)


@frappe.whitelist()
def list_chatbot_flows(account: str, start: int | None = 0, limit: int | None = None) -> list:
	_require_manager()
	_assert_account_access(account)
	from nudg.services.chatbot_setup import list_flows

	return list_flows(account, start=start, limit=limit)


@frappe.whitelist()
def save_chatbot_flow(account: str, payload) -> dict:
	_require_manager()
	_assert_account_access(account)
	from nudg.services.chatbot_setup import save_flow

	return save_flow(account, _chatbot_payload(payload))


@frappe.whitelist()
def delete_chatbot_flow(account: str, name: str) -> dict:
	_require_manager()
	_assert_account_access(account)
	from nudg.services.chatbot_setup import delete_flow

	return delete_flow(account, name)


@frappe.whitelist()
def list_chatbot_handoffs(account: str) -> dict:
	_require_manager()
	_assert_account_access(account)
	from nudg.services.chatbot_setup import list_handoffs

	return list_handoffs(account)


@frappe.whitelist()
def resume_chatbot_handoff(account: str, name: str) -> dict:
	_require_manager()
	_assert_account_access(account)
	from nudg.services.chatbot_setup import resume_handoff

	return resume_handoff(account, name)


@frappe.whitelist()
def cancel_chatbot_session(account: str, name: str) -> dict:
	_require_manager()
	_assert_account_access(account)
	from nudg.services.chatbot_setup import cancel_session

	return cancel_session(account, name)


@frappe.whitelist()
def directory_access() -> dict:
	"""Read, write, create, and delete from Role Permission Manager."""
	_require_login()
	from nudg.services.directory import access

	return access()


@frappe.whitelist()
def list_directory_profiles(account: str | None = None, query: str | None = None) -> list:
	_require_login()
	from nudg.services.directory import list_profiles

	return list_profiles(account, query)


@frappe.whitelist()
def save_directory_profile(
	phone_number: str | None = None,
	whatsapp_account: str | None = None,
	profile_name: str | None = None,
	status: str | None = None,
	name: str | None = None,
) -> dict:
	_require_login()
	from nudg.services.directory import save_profile

	return save_profile(name, profile_name, phone_number, whatsapp_account, status)


@frappe.whitelist()
def delete_directory_profile(name: str) -> dict:
	_require_login()
	from nudg.services.directory import delete_profile

	return delete_profile(name)


@frappe.whitelist()
def list_directory_recipient_lists(account: str | None = None, query: str | None = None) -> list:
	_require_login()
	from nudg.services.directory import list_recipient_lists

	return list_recipient_lists(account, query)


@frappe.whitelist()
def get_directory_recipient_list(name: str) -> dict:
	_require_login()
	from nudg.services.directory import get_recipient_list

	return get_recipient_list(name)


@frappe.whitelist()
def save_directory_recipient_list(
	list_name: str | None = None,
	description: str | None = None,
	whatsapp_account: str | None = None,
	recipients: str | list | None = None,
	name: str | None = None,
) -> dict:
	_require_login()
	from nudg.services.directory import save_recipient_list

	return save_recipient_list(name, list_name, description, whatsapp_account, recipients)


@frappe.whitelist()
def delete_directory_recipient_list(name: str) -> dict:
	_require_login()
	from nudg.services.directory import delete_recipient_list

	return delete_recipient_list(name)
