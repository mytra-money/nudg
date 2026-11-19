# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Incoming WA Message handler for the native chatbot."""

from __future__ import annotations

import json
from contextlib import contextmanager

import frappe

_processing_messages: set[str] = set()


def customer_phone(doc) -> str | None:
	"""The customer's number. On an official WA Message, `to` is the profile."""
	profile = getattr(doc, "to", None)
	if profile and frappe.db.exists("DocType", "WA Profile"):
		phone = frappe.db.get_value("WA Profile", profile, "phone_number")
		if phone:
			return str(phone)
	raw = getattr(doc, "from", None)
	return str(raw) if raw else (str(profile) if profile else None)


def content_kind(doc) -> str:
	"""text, button, or flow. Media and reactions are left alone."""
	if getattr(doc, "reaction", None):
		return "reaction"
	if getattr(doc, "media_id", None) or getattr(doc, "mime_type", None):
		return "media"
	raw = getattr(doc, "nudg_flow_response", None)
	if raw:
		return "flow"
	message = getattr(doc, "message", None) or ""
	if message.startswith("{") and "flow_token" in message:
		return "flow"
	return "text"


class ChatbotProcessor:
	def __init__(self, message_data: dict):
		self.message_data = message_data
		self.message_name = message_data.get("name")
		self.phone_number = message_data.get("from") or message_data.get("phone_number")
		self.message_text = message_data.get("message") or ""
		self.content_type = message_data.get("content_type") or "text"
		self.account = message_data.get("whatsapp_account")
		self.button_payload = message_data.get("button_payload")
		self.flow_response = _load_flow(message_data.get("flow_response"))
		if self.content_type == "button" and not self.button_payload:
			self.button_payload = self.message_text
		self.settings = None

	def get_chatbot_settings(self):
		if self.settings is not None:
			return self.settings or None
		try:
			from nudg.services.chatbot import get_settings

			settings = get_settings(self.account)
			if settings and settings.enabled:
				self.settings = settings
				return settings
		except Exception:
			frappe.log_error(title="Chatbot settings could not be read")
		self.settings = False
		return None

	def should_process(self) -> bool:
		settings = self.get_chatbot_settings()
		if not settings or not self.phone_number or not self.account:
			return False
		if self.content_type not in ("text", "button", "flow"):
			return False
		if settings.whatsapp_account != self.account:
			return False
		excluded = [row.phone_number for row in (settings.excluded_numbers or [])]
		if self.phone_number in excluded:
			return False
		return not self.is_transferred_to_agent()

	def is_transferred_to_agent(self) -> bool:
		try:
			filters = {"phone_number": self.phone_number, "status": "Active"}
			if self.account:
				filters["whatsapp_account"] = self.account
			return bool(frappe.db.exists("WA Agent Transfer", filters))
		except Exception:
			return False

	def process(self):
		settings = self.get_chatbot_settings()
		if not settings or not self.should_process():
			return

		if settings.business_hours_only and not self.is_business_hours():
			if settings.out_of_hours_message:
				self.send_response(settings.out_of_hours_message)
			return

		from nudg.chatbot.flow_engine import FlowEngine
		from nudg.chatbot.keyword_matcher import KeywordMatcher
		from nudg.chatbot.session_manager import SessionManager

		session_mgr = SessionManager(self.phone_number, self.account)
		keyword_matcher = KeywordMatcher(self.account)
		flow_engine = FlowEngine(self.phone_number, self.account)

		active = session_mgr.get_active_session()
		if active:
			if self.content_type == "flow" and self.flow_response:
				response = self.process_flow_response_in_session(active, flow_engine)
			else:
				response = flow_engine.process_input(active, self.message_text, self.button_payload)
			if response:
				self.send_response(response)
				return

		keyword = keyword_matcher.match(self.message_text)
		if keyword:
			if keyword.response_type == "Flow":
				response = flow_engine.start_flow(keyword.trigger_flow)
			else:
				response = self.build_keyword_response(keyword)
			if response:
				self.send_response(response)
				return

		triggered = flow_engine.check_flow_trigger(self.message_text, self.button_payload)
		if triggered:
			response = flow_engine.start_flow(triggered)
			if response:
				self.send_response(response)
				return

		if settings.enable_ai:
			try:
				from nudg.chatbot.ai_responder import AIResponder

				reply = AIResponder(settings, phone_number=self.phone_number).generate_response(
					self.message_text,
					session_mgr.get_conversation_history(),
				)
				if reply:
					self.send_response(reply)
					return
			except Exception:
				frappe.log_error(title="Chatbot AI fallback failed")

		if settings.default_response:
			self.send_response(settings.default_response)

	def process_flow_response_in_session(self, session, flow_engine):
		try:
			flow = frappe.get_doc("WA Chatbot Flow", session.current_flow)
			current = flow_engine._find_step(flow, session.current_step)
			if not current:
				return flow_engine.complete_flow(session, flow)
			if current.input_type != "WhatsApp Flow":
				return flow_engine.process_input(session, self.message_text, self.button_payload)
			data = flow_engine.process_flow_response(current, session, self.flow_response)
			session.session_data = json.dumps(data)
			session.add_message("Incoming", f"Flow completed: {self.message_text}", current.step_name)
			return flow_engine.process_input(session, self.message_text, None)
		except Exception:
			frappe.log_error(title="Chatbot flow response failed")
			return "An error occurred processing your form. Please try again."

	def build_keyword_response(self, keyword_doc):
		kind = keyword_doc.response_type
		if kind == "Text":
			return keyword_doc.response_text
		if kind == "Template":
			response = {
				"use_template": 1,
				"template": keyword_doc.response_template,
				"message_type": "Template",
			}
			if keyword_doc.template_parameters:
				response["body_param"] = keyword_doc.template_parameters
			return response
		if kind == "Media":
			media_type = (keyword_doc.media_type or "Image").lower()
			response = {
				"content_type": media_type,
				"message": keyword_doc.media_caption or "",
			}
			response[f"media_{media_type}"] = keyword_doc.media_url
			return response
		if kind == "Script":
			return self.execute_script(keyword_doc.script)
		return None

	def execute_script(self, script):
		if not script or not self.message_name:
			return None
		try:
			message_doc = frappe.get_doc("WA Message", self.message_name)
			if frappe.db.exists("Server Script", {"name": script, "script_type": "API"}):
				server_script = frappe.get_doc("Server Script", script)
				from frappe.utils.safe_exec import safe_exec

				locals_ = {
					"doc": message_doc,
					"phone_number": self.phone_number,
					"message": self.message_text,
					"account": self.account,
					"response": None,
				}
				safe_exec(server_script.script, _locals=locals_, script_filename=server_script.name)
				return locals_.get("response") or (frappe.response or {}).get("message")
			return frappe.call(script, doc=message_doc)
		except Exception:
			frappe.log_error(title=f"Chatbot script failed: {script}")
			return None

	def send_response(self, response):
		try:
			if isinstance(response, str):
				send_text(self.phone_number, self.account, response)
				return
			if not isinstance(response, dict):
				return
			if response.get("use_template") or response.get("message_type") == "Template":
				send_template(self.phone_number, response.get("template"), response.get("body_param"), self.account)
				return
			if response.get("content_type") == "interactive" or response.get("buttons"):
				send_buttons(self.phone_number, self.account, response.get("message") or "", response.get("buttons"))
				return
			if response.get("content_type") == "flow":
				cta = response.get("flow_cta") or "Open Form"
				flow_name = response.get("flow") or ""
				text = (response.get("message") or "Please complete the form.").strip()
				send_text(self.phone_number, self.account, f"{text}\n\n{cta}: {flow_name}".strip())
				return
			attach = (
				response.get("media_image")
				or response.get("media_video")
				or response.get("media_audio")
				or response.get("media_document")
			)
			if attach:
				from nudg.integrations.whatsapp import adapter

				adapter.send_message(
					to=self.phone_number,
					message=response.get("message") or "",
					attach=attach,
					content_type=response.get("content_type") or "document",
				)
				return
			if response.get("message"):
				send_text(self.phone_number, self.account, response["message"])
		except Exception:
			frappe.log_error(title="Chatbot reply failed")

	def is_business_hours(self) -> bool:
		settings = self.get_chatbot_settings()
		if not settings or not settings.business_hours:
			return True
		try:
			from datetime import datetime

			now = datetime.now()
			day_name = now.strftime("%A")
			for row in settings.business_hours:
				if row.day != day_name:
					continue
				if not row.enabled:
					return False
				start = _parse_time(row.start_time)
				end = _parse_time(row.end_time)
				if start and end:
					return start <= now.time() <= end
				return True
			return False
		except Exception:
			frappe.log_error(title="Chatbot business hours check failed")
			return True


@contextmanager
def _send_as_system():
	"""The inbound webhook is Guest. Official send requires a user who can create WA Message."""
	previous = getattr(getattr(frappe, "session", None), "user", None)
	if previous == "Administrator":
		yield
		return
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		if previous:
			frappe.set_user(previous)


def send_text(phone, account, message: str) -> str | None:
	if not phone or not message:
		return None
	from nudg.integrations.whatsapp import adapter

	with _send_as_system():
		return adapter.send_message(to=phone, message=message, account=account)


def send_template(phone, template, parameters=None, account=None) -> str | None:
	if not phone or not template:
		return None
	from nudg.integrations.whatsapp import adapter
	from nudg.services.campaigns import build_template_body_components

	with _send_as_system():
		return adapter.send_template(
			template=template,
			to=phone,
			account=account,
			components=build_template_body_components(parameters),
		)


def send_buttons(phone, account, message: str, buttons) -> str | None:
	"""Submit an official WA Message with reply buttons. Falls back to numbered text."""
	if isinstance(buttons, str):
		try:
			buttons = json.loads(buttons)
		except json.JSONDecodeError:
			buttons = []
	rows = []
	for button in buttons or []:
		if isinstance(button, str):
			title = button
			button_id = button
		else:
			title = button.get("title") or button.get("id") or ""
			button_id = button.get("id") or title
		if title:
			rows.append({"title": str(title)[:20], "button_id": str(button_id)[:256]})
	if not rows or not frappe.db.exists("DocType", "WA Message"):
		lines = [message] + [f"{index}. {row['title']}" for index, row in enumerate(rows, 1)]
		return send_text(phone, account, "\n".join(line for line in lines if line))

	with _send_as_system():
		return _send_buttons(phone, account, message, rows)


def _send_buttons(phone, account, message, rows) -> str | None:
	from whatsapp.whatsapp.api.messages import _resolve_to_profile, _submit

	from nudg.integrations.whatsapp.adapter import profile_on_account

	profile = _resolve_to_profile(profile_on_account(phone, account), create_if_missing=True)
	if not profile:
		return send_text(phone, account, message)
	doc = frappe.new_doc("WA Message")
	doc.update({
		"to": profile,
		"message": message or "Choose an option",
		"whatsapp_account": account,
		"direction": "Outgoing",
	})
	for row in rows[:3]:
		doc.append("interactive_buttons", row)
	doc.flags.ignore_chatbot = True
	doc.insert(ignore_permissions=True)
	_submit(doc, f"Failed to send chatbot buttons to {profile}")
	return doc.name


def process_incoming_message(doc, method=None):
	"""after_insert hook. Never raises, so a bot error cannot drop the inbound message."""
	try:
		if getattr(doc, "direction", None) != "Incoming":
			return
		if getattr(getattr(doc, "flags", None), "ignore_chatbot", False):
			return
		name = getattr(doc, "name", None)
		if not name or name in _processing_messages:
			return
		kind = content_kind(doc)
		if kind not in ("text", "button", "flow"):
			return
		account = getattr(doc, "whatsapp_account", None)
		if not account or not frappe.db.exists("DocType", "WA Chatbot"):
			return
		if not frappe.db.get_value("WA Chatbot", {"whatsapp_account": account}, "enabled"):
			return
		extra = inbound_extras(getattr(doc, "message_id", None))
		kind = extra.get("content_type") or kind
		payload = {
			"name": name,
			"from": customer_phone(doc),
			"message": getattr(doc, "message", "") or "",
			"content_type": kind,
			"whatsapp_account": getattr(doc, "whatsapp_account", None),
			"button_payload": extra.get("button_payload"),
			"flow_response": extra.get("flow_response") or getattr(doc, "nudg_flow_response", None),
		}
		_processing_messages.add(name)
		try:
			ChatbotProcessor(payload).process()
		finally:
			_processing_messages.discard(name)
	except Exception:
		frappe.log_error(title="Chatbot incoming handler failed")


def run_processor(message_data):
	"""Background entry kept for queued retries."""
	name = (message_data or {}).get("name", "unknown")
	try:
		ChatbotProcessor(message_data or {}).process()
	except Exception:
		frappe.log_error(title=f"Chatbot processor failed: {name}")
	finally:
		_processing_messages.discard(name)


def inbound_extras(message_id: str | None) -> dict:
	"""Button id and Flow JSON from the webhook body for this message id."""
	payload = getattr(getattr(frappe, "flags", None), "nudg_webhook_payload", None) or {}
	if not message_id or not isinstance(payload, dict):
		return {}
	for entry in payload.get("entry") or []:
		for change in entry.get("changes") or []:
			for msg in (change.get("value") or {}).get("messages") or []:
				if msg.get("id") != message_id:
					continue
				interactive = msg.get("interactive") or {}
				kind = interactive.get("type")
				if msg.get("type") == "button":
					button = msg.get("button") or {}
					return {"content_type": "button", "button_payload": button.get("payload") or button.get("text")}
				if kind == "button_reply":
					reply = interactive.get("button_reply") or {}
					return {"content_type": "button", "button_payload": reply.get("id") or reply.get("title")}
				if kind == "list_reply":
					reply = interactive.get("list_reply") or {}
					return {"content_type": "button", "button_payload": reply.get("id") or reply.get("title")}
				if kind == "nfm_reply":
					raw = (interactive.get("nfm_reply") or {}).get("response_json")
					parsed = _load_flow(raw)
					return {"content_type": "flow", "flow_response": parsed or raw}
	return {}


def _load_flow(value):
	if not value:
		return None
	if isinstance(value, dict):
		return value
	try:
		parsed = json.loads(value)
	except (TypeError, json.JSONDecodeError):
		return None
	return parsed if isinstance(parsed, dict) else None


def _parse_time(value):
	from datetime import time, timedelta

	if value in (None, ""):
		return None
	if isinstance(value, time):
		return value
	if isinstance(value, timedelta):
		total = int(value.total_seconds())
		return time(total // 3600, (total % 3600) // 60, total % 60)
	if not isinstance(value, str):
		return None
	parts = value.split(":")
	try:
		return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
	except (ValueError, IndexError):
		return None
