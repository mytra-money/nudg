"""Whitelisted APIs for Phase 2 product modules. Guests are rejected."""

from __future__ import annotations

import json

import frappe
from frappe import _

from nudg.services import (
	analytics,
	assignments,
	automation,
	campaigns,
	catalog as catalog_service,
	quick_replies,
)


def _require_login():
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to open Nudg."), frappe.PermissionError)


def _require_manager():
	"""Broadcasts, automation, catalogs, accounts, and team changes are manager work."""
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


@frappe.whitelist()
def list_catalogs(account: str | None = None) -> list:
	_require_manager()
	return catalog_service.list_catalogs(account)


@frappe.whitelist()
def list_catalog_items(catalog: str | None = None, status: str | None = "Active") -> list:
	_require_login()
	return catalog_service.list_items(catalog, status)


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
				"Catalog '{0}' has no Meta Catalog ID. Set the numeric id from Meta Commerce Manager in Integrations → Catalogs. "
				"Every product in this catalog is blocked for that reason."
			).format(catalog_name)
		)
	elif not catalog_id.isdigit():
		problems.append(
			_(
				"Catalog '{0}' has Meta Catalog ID '{1}', which is not a numeric Meta Commerce catalog id. "
				"Update it in Integrations → Catalogs. Every product in this catalog is blocked for that reason."
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
def list_quick_replies(account: str | None = None, status: str | None = "Active") -> list:
	_require_login()
	return quick_replies.list_quick_replies(account, status)


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
	return assignments.assign_conversation(profile, user, source="Manual")


@frappe.whitelist()
def unassign_conversation(profile: str) -> dict:
	_require_login()
	return assignments.unassign_conversation(profile)


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
		"callback_method": "nudg.integrations.webhook.handler",
		"verify_token": token,
	}


@frappe.whitelist()
def auto_assign_round_robin(profile: str) -> dict:
	"""Whitelisted API: Auto-route conversation using round-robin distribution."""
	_require_login()
	return assignments.auto_assign_round_robin(profile)


@frappe.whitelist()
def list_campaigns(account: str | None = None) -> list:
	_require_manager()
	return campaigns.list_campaigns(account)


@frappe.whitelist()
def get_campaign(name: str) -> dict:
	_require_manager()
	return campaigns.get_campaign(name)


@frappe.whitelist()
def run_campaign(name: str) -> dict:
	_require_manager()
	return campaigns.enqueue_run(name)


@frappe.whitelist()
def create_campaign(
	name: str,
	campaign_description: str | None = None,
	whatsapp_account: str | None = None,
	whatsapp_template: str | None = None,
	scheduled_at: str | None = None,
	recipients: str | list | None = None,
) -> dict:
	"""Create a draft broadcast from the Marketing screen."""
	_require_manager()
	return campaigns.create_campaign(
		name, campaign_description, whatsapp_account, whatsapp_template, scheduled_at, recipients
	)


@frappe.whitelist()
def update_campaign(
	name: str,
	campaign_name: str | None = None,
	campaign_description: str | None = None,
	whatsapp_account: str | None = None,
	whatsapp_template: str | None = None,
	scheduled_at: str | None = None,
	recipients: str | list | None = None,
) -> dict:
	_require_manager()
	return campaigns.update_campaign(
		name, campaign_name, campaign_description, whatsapp_account, whatsapp_template, scheduled_at, recipients
	)


@frappe.whitelist()
def delete_campaign(name: str) -> dict:
	"""Delete a draft, scheduled, or cancelled campaign."""
	_require_manager()
	return campaigns.delete_campaign(name)


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
	catalog = frappe.db.get_value("WA Catalog Item", name, "catalog")
	account = frappe.db.get_value("WA Catalog", catalog, "whatsapp_account") if catalog else None
	if account:
		_assert_account_access(account)
	frappe.delete_doc("WA Catalog Item", name, ignore_permissions=True, force=True)
	return {"name": name, "deleted": True}


@frappe.whitelist()
def list_automation_rules(account: str | None = None) -> list:
	_require_manager()
	return automation.list_rules(account)


@frappe.whitelist()
def create_automation_rule(
	rule_name: str,
	trigger: str,
	action: str,
	action_reference: str | None = None,
	whatsapp_account: str | None = None,
	status: str | None = None,
	condition_operator: str | None = None,
	condition_keyword: str | None = None,
) -> dict:
	_require_manager()
	return automation.create_rule(
		rule_name,
		trigger,
		action,
		action_reference,
		whatsapp_account,
		status,
		condition_operator,
		condition_keyword,
	)


@frappe.whitelist()
def update_automation_rule(
	name: str,
	rule_name: str | None = None,
	trigger: str | None = None,
	action: str | None = None,
	action_reference: str | None = None,
	whatsapp_account: str | None = None,
	status: str | None = None,
	condition_operator: str | None = None,
	condition_keyword: str | None = None,
) -> dict:
	_require_manager()
	return automation.update_rule(
		name,
		rule_name,
		trigger,
		action,
		action_reference,
		whatsapp_account,
		status,
		condition_operator,
		condition_keyword,
	)


@frappe.whitelist()
def delete_automation_rule(name: str) -> dict:
	_require_manager()
	name = (name or "").strip()
	if not name or not frappe.db.exists("WA Automation Rule", name):
		frappe.throw(_("Automation rule not found."))
	account = frappe.db.get_value("WA Automation Rule", name, "whatsapp_account")
	if account:
		_assert_account_access(account)
	frappe.delete_doc("WA Automation Rule", name, ignore_permissions=True, force=True)
	return {"name": name, "deleted": True}


@frappe.whitelist()
def list_automation_runs(rule: str | None = None) -> list:
	_require_manager()
	return automation.list_runs(rule)


@frappe.whitelist()
def get_analytics(account: str | None = None) -> dict:
	"""Optimistic analytics: latest Ready snapshot plus any Refreshing row."""
	_require_login()
	return {
		"latest": analytics.latest_snapshot(account),
		"refreshing": analytics.refreshing_snapshot(account),
		"history": analytics.list_snapshots(account, limit=20),
	}


@frappe.whitelist()
def refresh_analytics(account: str | None = None) -> dict:
	_require_login()
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
		fields=["name", "account_name", "status", "phone_id", "business_id", "app_id", "auto_read_receipts"],
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

	# If no default account is set, set this as default
	if frappe.db.exists("DocType", "WA Settings"):
		current_default = frappe.db.get_single_value("WA Settings", "default_account")
		if not current_default:
			frappe.db.set_single_value("WA Settings", "default_account", doc.name)

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
	return {
		"name": doc.name,
		"account_name": doc.account_name,
		"status": doc.status,
		"phone_id": doc.phone_id,
		"business_id": doc.business_id,
		"app_id": doc.app_id,
		"auto_read_receipts": doc.auto_read_receipts,
	}


@frappe.whitelist()
def get_whatsapp_settings() -> dict:
	"""WA Settings values a manager can edit. The webhook secret is never returned."""
	_require_manager()
	if not frappe.db.exists("DocType", "WA Settings"):
		return {"callback_method": "nudg.integrations.webhook.handler"}
	doc = frappe.get_single("WA Settings")
	return {
		"default_account": doc.default_account or "",
		"whatsapp_api_url": doc.whatsapp_api_url or "",
		"whatsapp_api_version": doc.whatsapp_api_version or "",
		"webhook_verify_token": doc.webhook_verify_token or "",
		"has_webhook_secret": bool(doc.webhook_secret),
		"callback_method": "nudg.integrations.webhook.handler",
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
	_require_manager()
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
	buttons: str | list | None = None,
	name: str | None = None,
) -> dict:
	"""Create or update a WA Template. Saving submits it to Meta."""
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
	_apply_template_buttons(doc, buttons)
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	return {
		"name": doc.name,
		"template_label": doc.template_label,
		"template_name": doc.template_name,
		"status": doc.status,
		"whatsapp_account": doc.whatsapp_account,
	}


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
		"message": doc.message,
		"footer": doc.footer,
		"whatsapp_account": doc.whatsapp_account,
		"buttons": [
			{
				"button_type": row.button_type,
				"button_text": row.button_text,
				"url": row.url,
				"phone_number": row.phone_number,
			}
			for row in (doc.buttons or [])
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
) -> dict:
	"""Exchange an Embedded Signup code and connect the customer's WhatsApp account."""
	_require_manager()
	from nudg.integrations.embedded_signup import complete_signup

	return complete_signup(code, waba_id, phone_number_id, account_name)


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
def create_team_member(
	account: str,
	full_name: str,
	email: str,
	password: str,
	role: str = "WhatsApp User",
) -> dict:
	"""Create a new team user directly in Nudg with email, name, password, and scoped WA Account permission."""
	_require_manager()
	user = frappe.session.user
	from nudg.security import is_account_manager, ensure_account_user_permission, _get_roles

	if not is_account_manager(account, user) and "System Manager" not in _get_roles(user):
		frappe.throw(_("Only managers of account '{0}' can add team members.").format(account), frappe.PermissionError)

	email = (email or "").strip().lower()
	full_name = (full_name or "").strip()
	password = (password or "").strip()

	if not email or "@" not in email:
		frappe.throw(_("A valid email address is required."))
	if not full_name:
		frappe.throw(_("Full name is required."))
	if not password or len(password) < 6:
		frappe.throw(_("Password must be at least 6 characters."))

	target_role = "WhatsApp Manager" if role == "WhatsApp Manager" else "WhatsApp User"

	if frappe.db.exists("User", email):
		u = frappe.get_doc("User", email)
		u.first_name = full_name
	else:
		u = frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": full_name,
			"send_welcome_email": 0,
			"enabled": 1,
			"user_type": "System User",
		})
		u.insert(ignore_permissions=True)

	from frappe.utils.password import update_password
	update_password(email, password)

	u.roles = [r for r in u.roles if r.role not in ("WhatsApp User", "WhatsApp Manager")]
	u.append("roles", {"role": target_role})
	if u.name not in ("Administrator", "Guest"):
		from nudg.desk_access import profile_name_for_roles

		profile = profile_name_for_roles({row.role for row in u.roles})
		if profile:
			u.module_profile = profile
	u.flags.nudg_profile_set = True
	u.save(ignore_permissions=True)

	# Grant User Permission for this WA Account
	ensure_account_user_permission(account, email)

	return {
		"status": "success",
		"message": _("Team member {0} added successfully.").format(full_name),
		"email": email,
		"role": target_role,
		"account": account,
	}


@frappe.whitelist()
def update_team_member(
	account: str,
	email: str,
	role: str | None = None,
	enabled: int | None = None,
	new_password: str | None = None,
) -> dict:
	"""Update role, status, or password of a team member."""
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

	if new_password and len(new_password.strip()) >= 6:
		from frappe.utils.password import update_password
		update_password(email, new_password.strip())

	return {
		"status": "success",
		"message": _("Team member updated successfully."),
		"email": email,
	}
