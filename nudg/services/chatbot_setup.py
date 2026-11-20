# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Simple chatbot setup used by the Automation screen."""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import cint

_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MATCH = {"Exact", "Contains", "Starts With", "Regex"}
_INPUTS = {"Text", "Number", "Email", "Phone"}


def _account(account: str | None) -> str:
	name = (account or "").strip()
	if not name or not frappe.db.exists("WA Account", name):
		frappe.throw(_("Select a WhatsApp account."))
	return name


def _clock(value) -> str | None:
	if value is None or value == "":
		return None
	if hasattr(value, "total_seconds"):
		total = int(value.total_seconds()) % 86400
		hours, rem = divmod(total, 3600)
		return f"{hours:02d}:{rem // 60:02d}:00"
	text = str(value).strip()
	if len(text) == 5:
		text = f"{text}:00"
	return text or None


def _hours(rows) -> list[dict]:
	by_day = {}
	for row in rows or []:
		day = row.get("day") if isinstance(row, dict) else getattr(row, "day", None)
		if day not in _DAYS:
			continue
		start = _clock(row.get("start_time") if isinstance(row, dict) else getattr(row, "start_time", None))
		end = _clock(row.get("end_time") if isinstance(row, dict) else getattr(row, "end_time", None))
		by_day[day] = {
			"day": day,
			"enabled": cint(row.get("enabled") if isinstance(row, dict) else getattr(row, "enabled", 0)),
			"start_time": start or "",
			"end_time": end or "",
		}
	if not by_day:
		return [
			{
				"day": day,
				"enabled": 0 if day in ("Saturday", "Sunday") else 1,
				"start_time": "" if day in ("Saturday", "Sunday") else "09:00:00",
				"end_time": "" if day in ("Saturday", "Sunday") else "18:00:00",
			}
			for day in _DAYS
		]
	return [by_day.get(day) or {"day": day, "enabled": 0, "start_time": "", "end_time": ""} for day in _DAYS]


def get_bot(account: str | None) -> dict:
	account = _account(account)
	doc = frappe.db.get_value("WA Chatbot", {"whatsapp_account": account}, "name")
	if not doc:
		return {
			"whatsapp_account": account,
			"enabled": 0,
			"default_response": "",
			"business_hours_only": 0,
			"out_of_hours_message": "",
			"business_hours": _hours([]),
			"enable_ai": 0,
			"ai_provider": "",
			"has_ai_key": 0,
			"ai_model": "",
			"session_timeout_minutes": 30,
			"excluded_numbers": [],
		}
	bot = frappe.get_doc("WA Chatbot", doc)
	return {
		"whatsapp_account": account,
		"enabled": cint(bot.enabled),
		"default_response": bot.default_response or "",
		"business_hours_only": cint(bot.business_hours_only),
		"out_of_hours_message": bot.out_of_hours_message or "",
		"business_hours": _hours(bot.business_hours),
		"enable_ai": cint(bot.enable_ai),
		"ai_provider": bot.ai_provider or "",
		"has_ai_key": 1 if bot.get_password("ai_api_key", raise_exception=False) else 0,
		"ai_model": bot.ai_model or "",
		"session_timeout_minutes": cint(bot.session_timeout_minutes) or 30,
		"excluded_numbers": [row.phone_number for row in (bot.excluded_numbers or []) if row.phone_number],
	}


def save_bot(account: str | None, payload: dict) -> dict:
	account = _account(account)
	payload = payload or {}
	name = frappe.db.get_value("WA Chatbot", {"whatsapp_account": account}, "name")
	doc = frappe.get_doc("WA Chatbot", name) if name else frappe.new_doc("WA Chatbot")
	doc.whatsapp_account = account
	doc.enabled = cint(payload.get("enabled"))
	doc.default_response = (payload.get("default_response") or "").strip()
	doc.business_hours_only = cint(payload.get("business_hours_only"))
	doc.out_of_hours_message = (payload.get("out_of_hours_message") or "").strip()
	doc.enable_ai = cint(payload.get("enable_ai"))
	doc.ai_provider = payload.get("ai_provider") or ""
	doc.ai_model = (payload.get("ai_model") or "").strip()
	doc.session_timeout_minutes = cint(payload.get("session_timeout_minutes")) or 30
	key = (payload.get("ai_api_key") or "").strip()
	if key:
		doc.ai_api_key = key
	doc.set("business_hours", [])
	for row in _hours(payload.get("business_hours")):
		doc.append("business_hours", {
			"day": row["day"],
			"enabled": row["enabled"],
			"start_time": row["start_time"] or None,
			"end_time": row["end_time"] or None,
		})
	doc.set("excluded_numbers", [])
	seen = set()
	for phone in payload.get("excluded_numbers") or []:
		number = str(phone or "").strip()
		if not number or number in seen:
			continue
		seen.add(number)
		doc.append("excluded_numbers", {"phone_number": number})
	doc.save(ignore_permissions=True)
	return get_bot(account)


def list_keywords(account: str | None, start: int | None = 0, limit: int | None = None) -> list[dict]:
	from nudg.paging import page_limit, page_start

	account = _account(account)
	return frappe.get_all(
		"WA Keyword Reply",
		filters={"whatsapp_account": account},
		fields=["name", "title", "keywords", "match_type", "response_type", "response_text", "trigger_flow", "enabled", "priority"],
		order_by="priority desc, modified desc",
		limit_start=page_start(start),
		limit_page_length=page_limit(limit, default=50, maximum=50),
	)


def save_keyword(account: str | None, payload: dict) -> dict:
	account = _account(account)
	payload = payload or {}
	keywords = (payload.get("keywords") or "").strip()
	if not keywords:
		frappe.throw(_("Enter at least one keyword."))
	match_type = payload.get("match_type") or "Contains"
	if match_type not in _MATCH:
		frappe.throw(_("Choose how the keyword should match."))
	response_type = payload.get("response_type") or "Text"
	if response_type not in ("Text", "Flow"):
		frappe.throw(_("A keyword can send text or start a flow."))
	name = (payload.get("name") or "").strip()
	doc = frappe.get_doc("WA Keyword Reply", name) if name and frappe.db.exists("WA Keyword Reply", name) else frappe.new_doc("WA Keyword Reply")
	if doc.get("whatsapp_account") and doc.whatsapp_account != account:
		frappe.throw(_("This keyword belongs to another WhatsApp account."))
	doc.whatsapp_account = account
	doc.title = (payload.get("title") or keywords.split(",")[0]).strip()[:140]
	doc.keywords = keywords
	doc.match_type = match_type
	doc.response_type = response_type
	if response_type == "Text":
		doc.response_text = (payload.get("response_text") or "").strip()
		doc.trigger_flow = None
	else:
		doc.response_text = ""
		doc.trigger_flow = (payload.get("trigger_flow") or "").strip()
	doc.enabled = cint(payload.get("enabled", 1))
	doc.priority = cint(payload.get("priority"))
	doc.save(ignore_permissions=True)
	return {"name": doc.name}


def delete_keyword(account: str | None, name: str) -> dict:
	account = _account(account)
	if not name or not frappe.db.exists("WA Keyword Reply", name):
		frappe.throw(_("Keyword not found."))
	if frappe.db.get_value("WA Keyword Reply", name, "whatsapp_account") != account:
		frappe.throw(_("This keyword belongs to another WhatsApp account."))
	frappe.delete_doc("WA Keyword Reply", name, ignore_permissions=True, force=True)
	return {"name": name, "deleted": True}


def list_flows(account: str | None, start: int | None = 0, limit: int | None = None) -> list[dict]:
	from nudg.paging import page_limit, page_start

	account = _account(account)
	names = frappe.get_all(
		"WA Chatbot Flow",
		filters={"whatsapp_account": account},
		pluck="name",
		order_by="modified desc",
		limit_start=page_start(start),
		limit_page_length=page_limit(limit, default=50, maximum=50),
	)
	rows = []
	for name in names:
		doc = frappe.get_doc("WA Chatbot Flow", name)
		rows.append({
			"name": doc.name,
			"flow_name": doc.flow_name,
			"enabled": cint(doc.enabled),
			"trigger_keywords": doc.trigger_keywords or "",
			"initial_message": doc.initial_message or "",
			"completion_message": doc.completion_message or "",
			"cancel_keywords": doc.cancel_keywords or "",
			"steps": [
				{
					"step_name": step.step_name,
					"message": step.message,
					"input_type": step.input_type or "Text",
					"store_as": step.store_as or "",
				}
				for step in doc.steps
			],
		})
	return rows


def save_flow(account: str | None, payload: dict) -> dict:
	account = _account(account)
	payload = payload or {}
	flow_name = (payload.get("flow_name") or "").strip()
	if not flow_name:
		frappe.throw(_("Name the flow."))
	steps = payload.get("steps") or []
	if not steps:
		frappe.throw(_("Add at least one question."))
	name = (payload.get("name") or "").strip() or flow_name
	if frappe.db.exists("WA Chatbot Flow", name):
		doc = frappe.get_doc("WA Chatbot Flow", name)
		if doc.whatsapp_account and doc.whatsapp_account != account:
			frappe.throw(_("This flow belongs to another WhatsApp account."))
	else:
		doc = frappe.new_doc("WA Chatbot Flow")
		doc.flow_name = flow_name
	doc.whatsapp_account = account
	doc.enabled = cint(payload.get("enabled", 1))
	doc.trigger_keywords = (payload.get("trigger_keywords") or "").strip()
	doc.initial_message = (payload.get("initial_message") or "").strip()
	doc.completion_message = (payload.get("completion_message") or "").strip()
	doc.cancel_keywords = (payload.get("cancel_keywords") or "stop").strip()
	doc.set("steps", [])
	seen = set()
	for index, step in enumerate(steps, start=1):
		step_name = re.sub(r"[^A-Za-z0-9_]", "", (step.get("step_name") or f"step_{index}").strip()) or f"step_{index}"
		if step_name in seen:
			frappe.throw(_("Each question needs its own name."))
		seen.add(step_name)
		input_type = step.get("input_type") or "Text"
		if input_type not in _INPUTS:
			input_type = "Text"
		doc.append("steps", {
			"step_name": step_name,
			"message": (step.get("message") or "").strip() or _("Please reply."),
			"message_type": "Text",
			"input_type": input_type,
			"store_as": (step.get("store_as") or "").strip(),
			"retry_on_invalid": 1,
			"max_retries": 3,
		})
	doc.save(ignore_permissions=True)
	return {"name": doc.name}


def delete_flow(account: str | None, name: str) -> dict:
	account = _account(account)
	if not name or not frappe.db.exists("WA Chatbot Flow", name):
		frappe.throw(_("Flow not found."))
	if frappe.db.get_value("WA Chatbot Flow", name, "whatsapp_account") != account:
		frappe.throw(_("This flow belongs to another WhatsApp account."))
	frappe.delete_doc("WA Chatbot Flow", name, ignore_permissions=True, force=True)
	return {"name": name, "deleted": True}


def list_handoffs(account: str | None) -> dict:
	account = _account(account)
	transfers = frappe.get_all(
		"WA Agent Transfer",
		filters={"whatsapp_account": account},
		fields=["name", "phone_number", "status", "agent", "agent_name", "transferred_at", "notes"],
		order_by="modified desc",
		limit=30,
	)
	sessions = frappe.get_all(
		"WA Chatbot Session",
		filters={"whatsapp_account": account, "status": "Active"},
		fields=["name", "phone_number", "current_flow", "current_step", "last_activity"],
		order_by="last_activity desc",
		limit=30,
	)
	return {"transfers": transfers, "sessions": sessions}


def resume_handoff(account: str | None, name: str) -> dict:
	account = _account(account)
	if not name or not frappe.db.exists("WA Agent Transfer", name):
		frappe.throw(_("Handoff not found."))
	if frappe.db.get_value("WA Agent Transfer", name, "whatsapp_account") != account:
		frappe.throw(_("This handoff belongs to another WhatsApp account."))
	doc = frappe.get_doc("WA Agent Transfer", name)
	doc.status = "Resumed"
	doc.save(ignore_permissions=True)
	return {"name": doc.name, "status": doc.status}


def cancel_session(account: str | None, name: str) -> dict:
	account = _account(account)
	if not name or not frappe.db.exists("WA Chatbot Session", name):
		frappe.throw(_("Session not found."))
	if frappe.db.get_value("WA Chatbot Session", name, "whatsapp_account") != account:
		frappe.throw(_("This session belongs to another WhatsApp account."))
	doc = frappe.get_doc("WA Chatbot Session", name)
	doc.status = "Cancelled"
	doc.save(ignore_permissions=True)
	return {"name": doc.name, "status": doc.status}
