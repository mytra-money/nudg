# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Automation rules, keyword matching, business hours, and persisted runs."""

from __future__ import annotations

import datetime
import json
import logging
import re
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from nudg.integrations.whatsapp import adapter
from nudg.services import assignments, quick_replies

logger = logging.getLogger("nudg.services.automation")


def _safe_now():
	try:
		return now_datetime()
	except Exception:
		return datetime.datetime.now()


def list_rules(account: str | None = None) -> list[dict]:
	frappe.has_permission("WA Automation Rule", "read", throw=True)
	filters = {}
	if account:
		filters["whatsapp_account"] = account
	rows = frappe.get_list(
		"WA Automation Rule",
		filters=filters,
		fields=[
			"name",
			"rule_name",
			"trigger",
			"action",
			"action_reference",
			"status",
			"whatsapp_account",
			"condition_operator",
			"condition_json",
			"modified",
		],
		order_by="modified desc",
		limit_page_length=100,
	)
	for row in rows:
		row["condition_keyword"] = _keyword_from_condition(row.get("condition_json"))
	return rows


def list_runs(rule: str | None = None, limit: int = 50) -> list[dict]:
	frappe.has_permission("WA Automation Run", "read", throw=True)
	filters = {}
	if rule:
		filters["rule"] = rule
	return frappe.get_list(
		"WA Automation Run",
		filters=filters,
		fields=[
			"name",
			"rule",
			"profile",
			"status",
			"started_at",
			"finished_at",
			"detail",
			"reference_message",
		],
		order_by="creation desc",
		limit_page_length=limit,
	)


def on_wa_message(doc, method=None):
	"""Evaluate Active rules when a WA Message is inserted or updated.

	Meta webhooks run as Guest. Rule actions need desk DocType permission, so
	work is enqueued as Administrator when the session is Guest.
	"""
	if not frappe.db.exists("DocType", "WA Automation Rule"):
		return
	if doc.get("reaction"):
		return

	trigger = None
	if method == "after_insert" and doc.direction == "Incoming":
		trigger = "Incoming Message"
	elif method == "on_update" and doc.status == "Failed":
		trigger = "Status Failed"
	if not trigger:
		return

	args = {
		"trigger": trigger,
		"profile": doc.to,
		"account": doc.whatsapp_account,
		"message_name": doc.name,
	}
	if getattr(getattr(frappe, "session", None), "user", None) == "Guest":
		frappe.enqueue(
			"nudg.services.automation.process_trigger",
			queue="short",
			enqueue_after_commit=True,
			**args,
		)
		return
	process_trigger(**args)


def process_trigger(trigger: str, profile: str | None, account: str | None, message_name: str | None):
	"""Fetch active rules matching the trigger event and execute qualified ones."""
	if not frappe.db.exists("DocType", "WA Automation Rule"):
		return

	# Support evaluating both 'Incoming Message', 'Keyword Match', and 'Keyword Rule' triggers on inbound messages
	trigger_filter: Any = trigger
	if trigger in ("Incoming Message", "Keyword Match", "Keyword Rule"):
		trigger_filter = ["in", ["Incoming Message", "Keyword Match", "Keyword Rule"]]

	rules = frappe.get_all(
		"WA Automation Rule",
		filters={"status": "Active", "trigger": trigger_filter},
		fields=["name", "action", "action_reference", "condition_json", "whatsapp_account", "trigger"],
	)

	doc = None
	if message_name:
		if frappe.db.exists("DocType", "WA Message") and frappe.db.exists("WA Message", message_name):
			doc = frappe.get_doc("WA Message", message_name)

	for rule in rules:
		if rule.whatsapp_account and account and rule.whatsapp_account != account:
			continue
		if doc and not _condition_matches(rule.condition_json, doc):
			continue
		if not doc and rule.condition_json and str(rule.condition_json).strip():
			continue
		_execute_rule(rule, profile=profile, message_name=message_name)


def evaluate_keyword_match(
	text: str | None,
	keyword: str | list[str],
	operator: str,
	case_sensitive: bool = False,
) -> bool:
	"""Evaluate message text against keyword(s) with Exact, Contains, Starts With, or Regex operators."""
	if text is None:
		text = ""
	text_val = str(text) if case_sensitive else str(text).lower()

	operators_normalized = {
		"exact": "Exact",
		"contains": "Contains",
		"starts with": "Starts With",
		"startswith": "Starts With",
		"regex": "Regex",
	}
	op = operators_normalized.get(str(operator).strip().lower(), operator)

	# Normalize keyword list
	keywords = keyword if isinstance(keyword, (list, tuple, set)) else [keyword]
	for kw in keywords:
		kw_str = str(kw) if case_sensitive else str(kw).lower()

		if op == "Exact":
			if text_val.strip() == kw_str.strip():
				return True
		elif op == "Contains":
			if kw_str in text_val:
				return True
		elif op == "Starts With":
			if text_val.strip().startswith(kw_str.strip()):
				return True
		elif op == "Regex":
			flags = 0 if case_sensitive else re.IGNORECASE
			try:
				if re.search(str(kw), str(text), flags=flags):
					return True
			except (re.error, OverflowError, ArithmeticError) as exc:
				logger.warning(f"Invalid regex '{kw}' in automation rule: {exc}")
				return False

	return False


def _get_doc_text(doc: Any) -> str:
	"""Safely extract plain text content from a WA Message or Desk Message record."""
	if doc is None:
		return ""
	if isinstance(doc, dict):
		return doc.get("message") or doc.get("content") or ""
	return getattr(doc, "message", None) or getattr(doc, "content", None) or (doc.get("message") if hasattr(doc, "get") else "") or ""


def _condition_matches(condition_json: str | None, doc: Any) -> bool:
	"""Evaluate JSON conditions against message doc.

	Supports:
	1. Nested keyword match:
	   {"keyword_match": {"operator": "Contains", "value": "ORDER", "case_sensitive": false}}
	2. Flat keyword condition:
	   {"operator": "Exact", "keyword": "HELP", "case_sensitive": false}
	3. Field-based operator:
	   {"field": "message", "operator": "Starts With", "value": "#"}
	4. Composite conditions combining keyword and doc field equality:
	   {"keyword_match": {"operator": "Contains", "value": "support"}, "direction": "Incoming"}
	5. Legacy key-value equality:
	   {"direction": "Incoming", "status": "Sent"}
	"""
	if not condition_json or not str(condition_json).strip():
		return True
	try:
		conditions = json.loads(condition_json)
	except (TypeError, ValueError):
		return False
	if not isinstance(conditions, dict):
		return False

	message_text = _get_doc_text(doc)

	# 1. Nested keyword match check
	if "keyword_match" in conditions:
		km = conditions["keyword_match"]
		if isinstance(km, dict):
			kw = km.get("value") or km.get("keyword") or km.get("values") or ""
			op = km.get("operator", "Contains")
			cs = bool(km.get("case_sensitive", False))
			target_field = km.get("field")
			text_to_eval = str(doc.get(target_field) or "") if target_field else message_text
			if not evaluate_keyword_match(text_to_eval, kw, op, case_sensitive=cs):
				return False

	# 2. Flat keyword condition check
	if "operator" in conditions and ("keyword" in conditions or "value" in conditions):
		kw = conditions.get("keyword") or conditions.get("value") or ""
		op = conditions.get("operator", "Contains")
		cs = bool(conditions.get("case_sensitive", False))
		target_field = conditions.get("field")
		text_to_eval = str(doc.get(target_field) or "") if target_field else message_text
		if not evaluate_keyword_match(text_to_eval, kw, op, case_sensitive=cs):
			return False

	# 3. Standard doc field conditions
	for key, expected in conditions.items():
		if key in ("keyword_match", "operator", "keyword", "value", "case_sensitive", "field"):
			continue
		doc_val = doc.get(key) if hasattr(doc, "get") else getattr(doc, key, None)
		if doc_val != expected:
			return False

	return True


def _execute_rule(rule: Any, profile: str | None, message_name: str | None):
	run = frappe.get_doc(
		{
			"doctype": "WA Automation Run",
			"rule": rule.name,
			"profile": profile,
			"status": "Queued",
			"started_at": _safe_now(),
			"reference_message": message_name,
		}
	)
	run.insert(ignore_permissions=True)

	try:
		detail = _run_action(rule, profile)
		run.status = "Success"
		run.detail = detail
	except Exception as exc:
		run.status = "Failed"
		run.detail = str(exc)[:500]
	run.finished_at = _safe_now()
	run.save(ignore_permissions=True)


def _run_action(rule: Any, profile: str | None) -> str:
	action = rule.action
	ref = rule.action_reference
	if action == "Assign":
		if not profile:
			frappe.throw(_("Automation Assign needs a profile."))
		user = ref or getattr(getattr(frappe, "session", None), "user", None) or "Administrator"
		assignments.assign_conversation(profile, user, source="Assignment Rule")
		return f"Assigned to {user}"
	if action == "Quick Reply":
		if not profile or not ref:
			frappe.throw(_("Automation Quick Reply needs a profile and quick reply name."))
		reply = quick_replies.use_quick_reply(ref)
		adapter.send_message(to=profile, message=reply["body"])
		return f"Sent quick reply {ref}"
	if action == "Send Template":
		if not profile or not ref:
			frappe.throw(_("Automation Send Template needs a profile and template name."))
		name = adapter.send_template(template=ref, to=profile)
		return f"Sent template message {name}"
	if action == "Send Text":
		if not profile or not ref:
			frappe.throw(_("Automation Send Text needs a profile and text content."))
		adapter.send_message(to=profile, message=ref)
		return f"Sent automated text response"
	frappe.throw(_("Unknown automation action {0}.").format(action))


_TRIGGERS = ("Incoming Message", "Status Failed", "Keyword Match", "Keyword Rule")
_ACTIONS = ("Send Template", "Assign", "Quick Reply", "Send Text")
_OPERATORS = ("Exact", "Contains", "Starts With", "Regex")


def _keyword_from_condition(raw: Any) -> str:
	if not raw:
		return ""
	try:
		data = json.loads(raw) if isinstance(raw, str) else raw
	except (TypeError, ValueError):
		return ""
	if not isinstance(data, dict):
		return ""
	nested = data.get("keyword_match")
	if isinstance(nested, dict):
		data = nested
	value = data.get("keyword") or data.get("value") or data.get("pattern") or ""
	if isinstance(value, (list, tuple)):
		return ", ".join(str(part) for part in value if str(part).strip())
	return str(value or "")


def _store_condition(operator: str | None, keyword: str | None) -> tuple[str, str]:
	op = operator if operator in _OPERATORS else "Contains"
	text = (keyword or "").strip()
	if not text:
		return op, ""
	return op, json.dumps({"operator": op, "keyword": text})


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


def _rule_dict(name: str) -> dict:
	row = frappe.db.get_value(
		"WA Automation Rule",
		name,
		[
			"name",
			"rule_name",
			"trigger",
			"action",
			"action_reference",
			"status",
			"whatsapp_account",
			"condition_operator",
			"condition_json",
			"modified",
		],
		as_dict=True,
	)
	if not row:
		return {"name": name, "rule_name": name}
	row["condition_keyword"] = _keyword_from_condition(row.get("condition_json"))
	return row


def create_rule(
	rule_name: str,
	trigger: str,
	action: str,
	action_reference: str | None = None,
	whatsapp_account: str | None = None,
	status: str | None = None,
	condition_operator: str | None = None,
	condition_keyword: str | None = None,
) -> dict:
	"""Create an automation rule from the Automation screen."""
	frappe.has_permission("WA Automation Rule", "create", throw=True)
	rule_name = (rule_name or "").strip()
	if not rule_name:
		frappe.throw(_("Rule name is required."))
	if trigger not in _TRIGGERS:
		frappe.throw(_("Choose a trigger."))
	if action not in _ACTIONS:
		frappe.throw(_("Choose an action."))
	if frappe.db.exists("WA Automation Rule", rule_name):
		frappe.throw(_("A rule named {0} already exists.").format(rule_name))
	operator, condition_json = _store_condition(condition_operator, condition_keyword)
	doc = frappe.get_doc(
		{
			"doctype": "WA Automation Rule",
			"rule_name": rule_name,
			"trigger": trigger,
			"action": action,
			"action_reference": (action_reference or "").strip(),
			"whatsapp_account": _account_or_throw(whatsapp_account),
			"status": "Inactive" if status == "Inactive" else "Active",
			"condition_operator": operator,
			"condition_json": condition_json,
		}
	)
	doc.insert()
	return _rule_dict(doc.name)


def update_rule(
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
	doc = frappe.get_doc("WA Automation Rule", name)
	frappe.has_permission("WA Automation Rule", "write", doc=doc, throw=True)
	new_name = (rule_name or "").strip() or doc.rule_name
	if new_name != doc.name:
		if frappe.db.exists("WA Automation Rule", new_name):
			frappe.throw(_("A rule named {0} already exists.").format(new_name))
		from frappe.model.rename_doc import rename_doc

		rename_doc("WA Automation Rule", doc.name, new_name, show_alert=False)
		doc = frappe.get_doc("WA Automation Rule", new_name)
	if trigger:
		if trigger not in _TRIGGERS:
			frappe.throw(_("Choose a trigger."))
		doc.trigger = trigger
	if action:
		if action not in _ACTIONS:
			frappe.throw(_("Choose an action."))
		doc.action = action
	doc.action_reference = (action_reference or "").strip()
	doc.whatsapp_account = _account_or_throw(whatsapp_account)
	if status in ("Active", "Inactive"):
		doc.status = status
	if condition_operator is not None or condition_keyword is not None:
		operator, condition_json = _store_condition(
			condition_operator or doc.condition_operator,
			condition_keyword if condition_keyword is not None else _keyword_from_condition(doc.condition_json),
		)
		doc.condition_operator = operator
		doc.condition_json = condition_json
	doc.save()
	return _rule_dict(doc.name)
