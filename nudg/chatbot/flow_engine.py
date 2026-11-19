# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Multi-step WhatsApp conversation flows."""

from __future__ import annotations

import json
import re
from datetime import datetime

import frappe

_BLOCKED_DOCTYPES = {
	"User",
	"Role",
	"DocType",
	"Custom Field",
	"Server Script",
	"Module Def",
	"System Settings",
	"WA Account",
	"WA Settings",
	"Email Account",
}


def parse_json(value, default=None):
	"""Accept a dict, a list, or a JSON string."""
	if value is None:
		return {} if default is None else default
	if isinstance(value, (dict, list)):
		return value
	if isinstance(value, str):
		text = value.strip()
		if not text:
			return {} if default is None else default
		try:
			return json.loads(text)
		except (json.JSONDecodeError, TypeError):
			return {} if default is None else default
	return {} if default is None else default


def validate_input(step, user_input, button_payload=None):
	"""Return (ok, error message)."""
	input_type = getattr(step, "input_type", None) or "None"
	if input_type == "Button":
		return (True, None) if (button_payload or user_input) else (False, "Please tap a button to continue.")
	if input_type == "WhatsApp Flow":
		return (True, None) if user_input else (False, "Please complete the form.")
	if input_type == "None":
		return True, None
	if not user_input:
		return False, "Please provide a response."

	if input_type == "Select" and getattr(step, "options", None):
		options = [item.strip().lower() for item in step.options.split("|") if item.strip()]
		if user_input.lower() not in options:
			return False, f"Please choose one of: {step.options.replace('|', ', ')}"
	elif input_type == "Number":
		cleaned = user_input.replace(",", "").replace(" ", "")
		if not re.match(r"^-?\d+\.?\d*$", cleaned):
			return False, "Please enter a valid number."
	elif input_type == "Email":
		if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", user_input.strip()):
			return False, "Please enter a valid email address."
	elif input_type == "Phone":
		cleaned = re.sub(r"[\s\-\(\)]", "", user_input)
		if not re.match(r"^\+?\d{10,15}$", cleaned):
			return False, "Please enter a valid phone number."
	elif input_type == "Date":
		valid = False
		for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
			try:
				datetime.strptime(user_input.strip(), fmt)
				valid = True
				break
			except ValueError:
				continue
		if not valid:
			return False, "Please enter a valid date (e.g., DD-MM-YYYY)."

	pattern = getattr(step, "validation_regex", None)
	if pattern:
		try:
			if not re.match(pattern, user_input):
				return False, getattr(step, "validation_error", None) or "Invalid format."
		except re.error:
			pass
	return True, None


def next_step_name(current_step, all_steps, user_input, button_payload=None):
	"""Name of the following step, from conditions, an explicit link, or row order."""
	conditions = parse_json(getattr(current_step, "conditional_next", None), {})
	if isinstance(conditions, dict) and conditions:
		response_key = button_payload or (user_input.lower() if user_input else "")
		if response_key in conditions:
			return conditions[response_key]
		lowered = str(response_key).lower()
		for key, target in conditions.items():
			if str(key).lower() == lowered:
				return target
		if "default" in conditions:
			return conditions["default"]

	explicit = getattr(current_step, "next_step", None)
	if explicit:
		return explicit

	ordered = sorted(all_steps, key=lambda step: getattr(step, "idx", 0) or 0)
	for index, step in enumerate(ordered):
		if step.step_name == current_step.step_name and index < len(ordered) - 1:
			return ordered[index + 1].step_name
	return None


def substitute(message: str, data: dict) -> str:
	text = message or ""
	for key, value in (data or {}).items():
		text = text.replace("{" + str(key) + "}", str(value))
	return text


class FlowEngine:
	def __init__(self, phone_number, whatsapp_account):
		self.phone_number = phone_number
		self.account = whatsapp_account

	def check_flow_trigger(self, message_text, button_payload=None):
		try:
			flows = frappe.get_all(
				"WA Chatbot Flow",
				filters={"enabled": 1},
				fields=["name", "trigger_keywords", "trigger_on_button", "whatsapp_account"],
			)
		except Exception:
			frappe.log_error(title="Chatbot flow lookup failed")
			return None

		for flow in flows:
			if not self.account or flow.whatsapp_account != self.account:
				continue
			if button_payload and flow.trigger_on_button and button_payload == flow.trigger_on_button:
				return flow.name
			if flow.trigger_keywords and message_text:
				keywords = [item.strip().lower() for item in flow.trigger_keywords.split(",") if item.strip()]
				if message_text.lower() in keywords:
					return flow.name
		return None

	def start_flow(self, flow_name):
		try:
			flow = frappe.get_doc("WA Chatbot Flow", flow_name)
			if not flow.steps:
				return None
			first = sorted(flow.steps, key=lambda step: step.idx or 0)[0]
			session = frappe.get_doc({
				"doctype": "WA Chatbot Session",
				"phone_number": self.phone_number,
				"whatsapp_account": self.account,
				"status": "Active",
				"current_flow": flow_name,
				"current_step": first.step_name,
				"session_data": json.dumps({}),
				"started_at": datetime.now(),
				"last_activity": datetime.now(),
			})
			session.insert(ignore_permissions=True)
			if flow.initial_message_type == "Template" and flow.initial_template:
				return {"use_template": 1, "template": flow.initial_template, "message_type": "Template"}
			parts = []
			if flow.initial_message:
				parts.append(flow.initial_message)
			step_message = self.build_step_message(first, session)
			if isinstance(step_message, str):
				if step_message:
					parts.append(step_message)
				return "\n\n".join(parts) if parts else step_message
			if parts:
				return parts[0]
			return step_message
		except Exception:
			frappe.log_error(title=f"Chatbot flow could not start: {flow_name}")
			return None

	def process_input(self, session, user_input, button_payload=None):
		try:
			flow = frappe.get_doc("WA Chatbot Flow", session.current_flow)
			if self._cancelled(flow, session, user_input):
				return "Your request has been cancelled."

			current = self._find_step(flow, session.current_step)
			if not current:
				return self.complete_flow(session, flow)

			if current.input_type and current.input_type != "None":
				ok, error = validate_input(current, user_input, button_payload)
				if not ok:
					session.step_retries = int(session.step_retries or 0) + 1
					limit = int(current.max_retries or 3)
					if current.retry_on_invalid and session.step_retries < limit:
						session.save(ignore_permissions=True)
						return error or current.validation_error or "Invalid input. Please try again."
					session.status = "Cancelled"
					session.completed_at = datetime.now()
					session.save(ignore_permissions=True)
					return "Too many invalid attempts. Please start again."
				if current.store_as:
					data = parse_json(session.session_data, {})
					data[current.store_as] = button_payload or user_input
					session.session_data = json.dumps(data)

			session.add_message("Incoming", user_input, current.step_name)
			following = next_step_name(current, flow.steps, user_input, button_payload)
			if not following:
				session.save(ignore_permissions=True)
				return self.complete_flow(session, flow)

			step = self._find_step(flow, following)
			if not step:
				return self.complete_flow(session, flow)

			data = parse_json(session.session_data, {})
			if step.skip_condition and self.evaluate_skip_condition(step.skip_condition, data):
				following = next_step_name(step, flow.steps, None, None)
				if not following:
					return self.complete_flow(session, flow)
				step = self._find_step(flow, following) or step

			session.current_step = step.step_name
			session.step_retries = 0
			session.last_activity = datetime.now()
			response = self.build_step_message(step, session)
			if isinstance(response, str):
				session.add_message("Outgoing", response, step.step_name)
			session.save(ignore_permissions=True)
			return response
		except Exception:
			frappe.log_error(title="Chatbot flow input failed")
			return "An error occurred. Please try again later."

	def process_flow_response(self, step, session, flow_response):
		"""Map a WhatsApp Flow field payload onto session variables."""
		data = parse_json(session.session_data, {})
		if not flow_response:
			return data
		mapping = parse_json(getattr(step, "flow_field_mapping", None), {})
		if isinstance(mapping, dict) and mapping:
			for session_var, flow_field in mapping.items():
				if flow_field in flow_response:
					data[session_var] = flow_response[flow_field]
		elif isinstance(flow_response, dict):
			data.update(flow_response)
		if getattr(step, "store_as", None):
			data[step.store_as] = flow_response
		return data

	def build_step_message(self, step, session):
		data = parse_json(session.session_data, {})
		message = substitute(step.message or "", data)
		if step.message_type == "Template" and step.template:
			return {"use_template": 1, "template": step.template, "message_type": "Template"}
		if step.message_type == "Script" and step.response_script:
			scripted = self.run_response_script(step.response_script, data, session)
			if scripted:
				return scripted
			return message
		if step.input_type == "Button" and step.buttons:
			buttons = parse_json(step.buttons, [])
			if buttons:
				return {"message": message, "content_type": "interactive", "buttons": buttons}
		if step.input_type == "WhatsApp Flow" and step.whatsapp_flow:
			return {
				"message": message,
				"content_type": "flow",
				"flow": step.whatsapp_flow,
				"flow_cta": step.flow_cta or "Open Form",
				"flow_screen": step.flow_screen or None,
			}
		if step.input_type == "Select" and step.options:
			message += f"\n\nOptions: {step.options.replace('|', ', ')}"
		return message

	def evaluate_skip_condition(self, condition, data) -> bool:
		try:
			return bool(
				frappe.safe_eval(
					condition,
					eval_globals={"data": data, "len": len, "str": str, "int": int, "float": float, "bool": bool},
					eval_locals={},
				)
			)
		except Exception:
			return False

	def complete_flow(self, session, flow):
		try:
			session.status = "Completed"
			session.completed_at = datetime.now()
			session.save(ignore_permissions=True)
			data = parse_json(session.session_data, {})
			action = flow.on_complete_action
			if action == "Create Document":
				self.create_document(flow, data)
			elif action == "Call API":
				self.call_api(flow.api_endpoint, data)
			elif action == "Run Script":
				self.run_script(flow.custom_script, data)
			return substitute(flow.completion_message or "Thank you! Your request has been submitted.", data)
		except Exception:
			frappe.log_error(title="Chatbot flow completion failed")
			return "Thank you! Your request has been received."

	def create_document(self, flow, data):
		target = flow.create_doctype
		mapping = parse_json(flow.field_mapping, {})
		if not target or not isinstance(mapping, dict) or not mapping:
			return None
		if target in _BLOCKED_DOCTYPES:
			frappe.log_error(title=f"Chatbot refused to create {target}")
			return None
		payload = {"doctype": target}
		for field, variable in mapping.items():
			if variable in data:
				payload[field] = data[variable]
		if len(payload) <= 1:
			return None
		doc = frappe.get_doc(payload)
		doc.insert(ignore_permissions=True)
		return doc.name

	def call_api(self, endpoint, data):
		if not endpoint:
			return
		from urllib import request as urlrequest

		body = json.dumps(data).encode()
		req = urlrequest.Request(
			endpoint,
			data=body,
			headers={"Content-Type": "application/json"},
			method="POST",
		)
		try:
			with urlrequest.urlopen(req, timeout=30) as response:
				response.read()
		except Exception:
			frappe.log_error(title="Chatbot completion API failed")

	def run_script(self, script, data):
		self._safe_script(script, {"data": data, "json": json, "response": None})

	def run_response_script(self, script, data, session):
		locals_ = {
			"data": data,
			"json": json,
			"session": session,
			"phone_number": self.phone_number,
			"response": None,
		}
		self._safe_script(script, locals_)
		return locals_.get("response")

	def _safe_script(self, script, locals_):
		if not script:
			return
		try:
			from frappe.utils.safe_exec import safe_exec

			safe_exec(script, _locals=locals_, script_filename="wa_chatbot_flow")
		except Exception:
			frappe.log_error(title="Chatbot flow script failed")

	def _cancelled(self, flow, session, user_input) -> bool:
		if not flow.cancel_keywords or not user_input:
			return False
		words = [word.strip().lower() for word in flow.cancel_keywords.split(",") if word.strip()]
		if user_input.lower() not in words:
			return False
		session.status = "Cancelled"
		session.completed_at = datetime.now()
		session.save(ignore_permissions=True)
		return True

	@staticmethod
	def _find_step(flow, step_name):
		for step in flow.steps:
			if step.step_name == step_name:
				return step
		return None
