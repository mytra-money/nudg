# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Catalog management, SPM/MPM interactive builders, and inbound cart order parsing."""

from __future__ import annotations

import logging
import re
from typing import Any

import frappe
from frappe import _

from nudg.integrations.whatsapp.catalog_adapter import sync_catalog

logger = logging.getLogger("nudg.services.catalog")


def list_catalogs(account: str | None = None) -> list[dict]:
	frappe.has_permission("WhatsApp Catalog", "read", throw=True)
	filters = {}
	if account:
		filters["whatsapp_account"] = account
	return frappe.get_list(
		"WhatsApp Catalog",
		filters=filters,
		fields=[
			"name",
			"catalog_name",
			"whatsapp_account",
			"status",
			"meta_catalog_id",
			"sync_status",
			"sync_error",
			"description",
			"modified",
		],
		order_by="modified desc",
		limit_page_length=100,
	)


def list_items(catalog: str | None = None, status: str | None = "Active") -> list[dict]:
	frappe.has_permission("WhatsApp Catalog Item", "read", throw=True)
	filters: dict = {}
	if catalog:
		filters["catalog"] = catalog
	if status:
		filters["status"] = status
	rows = frappe.get_list(
		"WhatsApp Catalog Item",
		filters=filters,
		fields=[
			"name",
			"catalog",
			"item_name",
			"sku",
			"description",
			"price",
			"currency",
			"image",
			"meta_retailer_id",
			"status",
			"sort_order",
		],
		order_by="sort_order asc, modified desc",
		limit_page_length=200,
	)
	catalog_names = list({row.get("catalog") for row in rows if row.get("catalog")})
	catalogs: dict[str, dict] = {}
	if catalog_names:
		for catalog_row in frappe.get_list(
			"WhatsApp Catalog",
			filters={"name": ["in", catalog_names]},
			fields=["name", "catalog_name", "meta_catalog_id"],
			limit_page_length=len(catalog_names),
		):
			catalogs[catalog_row.name] = catalog_row
	for row in rows:
		catalog_row = catalogs.get(row.get("catalog"))
		if not catalog_row:
			continue
		row["catalog_name"] = catalog_row.get("catalog_name")
		row["meta_catalog_id"] = catalog_row.get("meta_catalog_id")
	return rows


def request_sync(catalog: str) -> dict:
	if not catalog:
		frappe.throw(_("Catalog is required."))
	return sync_catalog(catalog)


# -----------------------------------------------------------------------------
# Interactive Commerce Message Builders (SPM & MPM)
# -----------------------------------------------------------------------------

def build_spm_payload(
	catalog_id: str,
	product_retailer_id: str,
	body_text: str | None = None,
	footer_text: str | None = None,
) -> dict[str, Any]:
	"""Build Meta Single-Product Message (SPM) interactive payload.

	Args:
		catalog_id: Meta Catalog ID (E.g. "9876543210").
		product_retailer_id: Product SKU or retailer ID in Meta Commerce Manager.
		body_text: Optional text describing the featured product.
		footer_text: Optional footer message (e.g. shipping policy).

	Returns:
		dict: Valid Meta Interactive Product specification dict.
	"""
	if not catalog_id:
		frappe.throw(_("Single-Product Message requires a valid catalog_id."))
	if not product_retailer_id:
		frappe.throw(_("Single-Product Message requires a product_retailer_id."))

	payload: dict[str, Any] = {
		"type": "product",
		"action": {
			"catalog_id": str(catalog_id),
			"product_retailer_id": str(product_retailer_id),
		},
	}
	if body_text:
		payload["body"] = {"text": str(body_text)}
	if footer_text:
		payload["footer"] = {"text": str(footer_text)}

	return payload


# Alias for explicit naming
build_single_product_message = build_spm_payload


def build_mpm_payload(
	catalog_id: str,
	sections: list[dict[str, Any]],
	body_text: str,
	header_text: str | None = None,
	footer_text: str | None = None,
) -> dict[str, Any]:
	"""Build Meta Multi-Product Message (MPM) interactive payload.

	Args:
		catalog_id: Meta Catalog ID.
		sections: List of section dicts. Each section must have 'title' and
		          either 'product_items' ([{"product_retailer_id": "SKU"}]) or
		          'product_retailer_ids' (["SKU1", "SKU2"]).
		body_text: Main catalog introduction text.
		header_text: Optional text header.
		footer_text: Optional footer text.

	Returns:
		dict: Valid Meta Interactive Product List specification dict.

	Raises:
		frappe.ValidationError if section/item count constraints are violated.
	"""
	if not catalog_id:
		frappe.throw(_("Multi-Product Message requires a valid catalog_id."))
	if not sections:
		frappe.throw(_("Multi-Product Message requires at least one product section."))
	if len(sections) > 10:
		frappe.throw(_("Meta limits Multi-Product Messages to at most 10 sections."))

	total_items = 0
	formatted_sections: list[dict[str, Any]] = []

	for sec in sections:
		title = (sec.get("title") or "Products").strip()
		if len(title) > 24:
			title = title[:24]

		items: list[dict[str, str]] = []
		if "product_items" in sec and isinstance(sec["product_items"], list):
			for it in sec["product_items"]:
				pid = it.get("product_retailer_id") if isinstance(it, dict) else str(it)
				if pid:
					items.append({"product_retailer_id": str(pid)})
		elif "product_retailer_ids" in sec and isinstance(sec["product_retailer_ids"], list):
			for pid in sec["product_retailer_ids"]:
				if pid:
					items.append({"product_retailer_id": str(pid)})

		if not items:
			continue

		total_items += len(items)
		formatted_sections.append({
			"title": title,
			"product_items": items,
		})

	if not formatted_sections:
		frappe.throw(_("No valid products found in sections for Multi-Product Message."))
	if total_items > 30:
		frappe.throw(_("Meta Multi-Product Messages can contain at most 30 products (found {0}).").format(total_items))

	payload: dict[str, Any] = {
		"type": "product_list",
		"body": {"text": str(body_text or "Check out our product catalog")},
		"action": {
			"catalog_id": str(catalog_id),
			"sections": formatted_sections,
		},
	}
	if header_text:
		payload["header"] = {"type": "text", "text": str(header_text)[:60]}
	if footer_text:
		payload["footer"] = {"text": str(footer_text)[:60]}

	return payload


# Alias for explicit naming
build_multi_product_message = build_mpm_payload


def send_single_product(
	channel: Any,
	to: str,
	catalog_id: str,
	product_retailer_id: str,
	body_text: str | None = None,
	footer_text: str | None = None,
) -> dict[str, Any]:
	"""Dispatch a Single-Product Message to a customer."""
	payload = build_spm_payload(catalog_id, product_retailer_id, body_text, footer_text)
	channel_doc = _resolve_channel_doc(channel)

	from nudg.integrations.connector.factory import get_connector
	connector = get_connector(channel_doc)
	return connector.send_interactive(channel_doc, to=to, interactive_payload=payload)


def send_multi_product(
	channel: Any,
	to: str,
	catalog_id: str,
	sections: list[dict[str, Any]],
	body_text: str,
	header_text: str | None = None,
	footer_text: str | None = None,
) -> dict[str, Any]:
	"""Dispatch a Multi-Product Message to a customer."""
	payload = build_mpm_payload(catalog_id, sections, body_text, header_text, footer_text)
	channel_doc = _resolve_channel_doc(channel)

	from nudg.integrations.connector.factory import get_connector
	connector = get_connector(channel_doc)
	return connector.send_interactive(channel_doc, to=to, interactive_payload=payload)


# -----------------------------------------------------------------------------
# Inbound Cart / Order Webhook Parser
# -----------------------------------------------------------------------------

def parse_inbound_order(order_data: dict[str, Any]) -> dict[str, Any]:
	"""Parse an incoming Meta 'order' webhook payload into structured cart data.

	Extracts:
	- catalog_id
	- customer_text
	- product_items (product_retailer_id, quantity, item_price, currency, line_total)
	- total_price
	- currency
	- summary_text (markdown formatted chat card representation)
	"""
	catalog_id = str(order_data.get("catalog_id") or "")
	customer_text = (order_data.get("text") or "").strip()
	raw_items = order_data.get("product_items") or []

	parsed_items: list[dict[str, Any]] = []
	total_price = 0.0
	currency = ""

	for item in raw_items:
		if not isinstance(item, dict):
			continue
		ret_id = str(item.get("product_retailer_id") or "")
		try:
			qty = float(item.get("quantity") or 1)
		except (ValueError, TypeError):
			qty = 1.0
		try:
			price = float(item.get("item_price") or 0.0)
		except (ValueError, TypeError):
			price = 0.0

		curr = str(item.get("currency") or "").upper()
		if curr and not currency:
			currency = curr

		line_total = qty * price
		total_price += line_total

		parsed_items.append({
			"product_retailer_id": ret_id,
			"quantity": qty,
			"item_price": price,
			"currency": curr,
			"line_total": line_total,
		})

	# Generate a readable markdown transcript representation
	clean_curr = re.sub(r"[\r\n\t]+", " ", str(currency)).strip()
	summary_lines = [
		f"🛒 Order Placed ({len(parsed_items)} item{'s' if len(parsed_items) != 1 else ''})"
	]
	if catalog_id:
		summary_lines.append(f"Catalog ID: {catalog_id}")

	for it in parsed_items:
		qty_str = str(int(it["quantity"])) if it["quantity"].is_integer() else f"{it['quantity']:.2f}"
		curr_symbol = it["currency"] or clean_curr
		summary_lines.append(f"  • {it['product_retailer_id']} × {qty_str} @ {curr_symbol} {it['item_price']:.2f} = {curr_symbol} {it['line_total']:.2f}")

	curr_total = clean_curr or ""
	summary_lines.append(f"Total: {curr_total} {total_price:.2f}".strip())

	if customer_text:
		summary_lines.append(f"Customer Note: {customer_text}")

	return {
		"catalog_id": catalog_id,
		"customer_text": customer_text,
		"product_items": parsed_items,
		"total_price": total_price,
		"currency": currency,
		"item_count": len(parsed_items),
		"summary_text": "\n".join(summary_lines),
	}


def _account_or_throw(account: str | None) -> str | None:
	account = (account or "").strip()
	if not account:
		return None
	if not frappe.db.exists("WA Account", account):
		frappe.throw(_("WhatsApp Account {0} was not found.").format(account))
	user = getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	if user == "Guest":
		frappe.throw(_("Log in to continue."), frappe.PermissionError)
	if user == "Administrator":
		return account
	roles = frappe.get_roles(user) if hasattr(frappe, "get_roles") else []
	if isinstance(roles, (list, tuple, set)) and "System Manager" in roles:
		return account
	from nudg.security import get_user_wa_accounts

	if account not in (get_user_wa_accounts(user) or []):
		frappe.throw(_("You cannot use WhatsApp Account {0}.").format(account), frappe.PermissionError)
	return account


def _catalog_dict(name: str) -> dict:
	row = frappe.db.get_value(
		"WhatsApp Catalog",
		name,
		["name", "catalog_name", "whatsapp_account", "status", "meta_catalog_id", "sync_status", "sync_error", "description", "modified"],
		as_dict=True,
	)
	return row or {"name": name}


def create_catalog(
	catalog_name: str,
	whatsapp_account: str | None = None,
	description: str | None = None,
	status: str | None = None,
) -> dict:
	"""Create a WhatsApp Catalog from the catalogs screen."""
	frappe.has_permission("WhatsApp Catalog", "create", throw=True)
	catalog_name = (catalog_name or "").strip()
	if not catalog_name:
		frappe.throw(_("Catalog name is required."))
	if frappe.db.exists("WhatsApp Catalog", catalog_name):
		frappe.throw(_("A catalog named {0} already exists.").format(catalog_name))
	chosen = status if status in ("Draft", "Active", "Archived") else "Draft"
	doc = frappe.get_doc(
		{
			"doctype": "WhatsApp Catalog",
			"catalog_name": catalog_name,
			"whatsapp_account": _account_or_throw(whatsapp_account),
			"description": (description or "").strip(),
			"status": chosen,
		}
	)
	doc.insert()
	return _catalog_dict(doc.name)


def update_catalog(
	name: str,
	catalog_name: str | None = None,
	whatsapp_account: str | None = None,
	description: str | None = None,
	status: str | None = None,
) -> dict:
	doc = frappe.get_doc("WhatsApp Catalog", name)
	frappe.has_permission("WhatsApp Catalog", "write", doc=doc, throw=True)
	new_name = (catalog_name or "").strip() or doc.catalog_name
	if new_name != doc.name:
		if frappe.db.exists("WhatsApp Catalog", new_name):
			frappe.throw(_("A catalog named {0} already exists.").format(new_name))
		from frappe.model.rename_doc import rename_doc

		rename_doc("WhatsApp Catalog", doc.name, new_name, show_alert=False)
		doc = frappe.get_doc("WhatsApp Catalog", new_name)
	if status in ("Draft", "Active", "Archived"):
		doc.status = status
	doc.whatsapp_account = _account_or_throw(whatsapp_account)
	doc.description = (description or "").strip()
	doc.save()
	return _catalog_dict(doc.name)


def _item_dict(name: str) -> dict:
	row = frappe.db.get_value(
		"WhatsApp Catalog Item",
		name,
		["name", "catalog", "item_name", "sku", "description", "price", "currency", "image", "meta_retailer_id", "status", "sort_order"],
		as_dict=True,
	)
	return row or {"name": name}


def create_catalog_item(
	catalog: str,
	item_name: str,
	sku: str | None = None,
	description: str | None = None,
	price: Any = None,
	currency: str | None = None,
	status: str | None = None,
	image: str | None = None,
) -> dict:
	frappe.has_permission("WhatsApp Catalog Item", "create", throw=True)
	catalog = (catalog or "").strip()
	item_name = (item_name or "").strip()
	if not catalog or not frappe.db.exists("WhatsApp Catalog", catalog):
		frappe.throw(_("Choose a catalog first."))
	catalog_doc = frappe.get_doc("WhatsApp Catalog", catalog)
	frappe.has_permission("WhatsApp Catalog", "read", doc=catalog_doc, throw=True)
	if not item_name:
		frappe.throw(_("Item name is required."))
	try:
		amount = float(price) if price not in (None, "") else 0
	except (TypeError, ValueError):
		frappe.throw(_("Price must be a number."))
	doc = frappe.get_doc(
		{
			"doctype": "WhatsApp Catalog Item",
			"catalog": catalog,
			"item_name": item_name,
			"sku": (sku or "").strip(),
			"description": (description or "").strip(),
			"price": amount,
			"currency": (currency or "INR").strip() or "INR",
			"status": "Inactive" if status == "Inactive" else "Active",
			"image": (image or "").strip(),
		}
	)
	doc.insert()
	return _item_dict(doc.name)


def update_catalog_item(
	name: str,
	item_name: str | None = None,
	sku: str | None = None,
	description: str | None = None,
	price: Any = None,
	currency: str | None = None,
	status: str | None = None,
	image: str | None = None,
) -> dict:
	doc = frappe.get_doc("WhatsApp Catalog Item", name)
	frappe.has_permission("WhatsApp Catalog Item", "write", doc=doc, throw=True)
	item_name = (item_name or "").strip()
	if not item_name:
		frappe.throw(_("Item name is required."))
	try:
		amount = float(price) if price not in (None, "") else 0
	except (TypeError, ValueError):
		frappe.throw(_("Price must be a number."))
	doc.item_name = item_name
	doc.sku = (sku or "").strip()
	doc.description = (description or "").strip()
	doc.price = amount
	doc.currency = (currency or doc.currency or "INR").strip() or "INR"
	if status in ("Active", "Inactive"):
		doc.status = status
	if image is not None:
		doc.image = (image or "").strip()
	doc.save()
	return _item_dict(doc.name)


def _resolve_channel_doc(channel: Any) -> Any:
	if isinstance(channel, dict):
		return channel
	if hasattr(channel, "name") or hasattr(channel, "phone_number_id"):
		return channel
	try:
		if isinstance(channel, str) and frappe.db and frappe.db.exists("WA Account", channel):
			return frappe.get_doc("WA Account", channel)
	except Exception:
		pass
	return channel
