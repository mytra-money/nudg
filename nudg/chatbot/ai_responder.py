# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Optional AI replies for the chatbot. Uses each provider's HTTP API."""

from __future__ import annotations

import json
from urllib import error, request

import frappe


class AIResponder:
	def __init__(self, settings, phone_number=None):
		self.settings = settings
		self.phone_number = phone_number
		self.provider = settings.ai_provider
		self.api_key = settings.get_password("ai_api_key") if settings.get("ai_api_key") else None
		self.model = settings.ai_model or "gpt-4o-mini"
		self.system_prompt = settings.ai_system_prompt or "You are a helpful assistant."
		self.max_tokens = int(settings.ai_max_tokens or 500)
		self.temperature = float(settings.ai_temperature or 0.7)
		self.include_history = bool(settings.ai_include_history)
		self.history_limit = int(settings.ai_history_limit or 4)
		self.current_message = ""

	def generate_response(self, message, conversation_history=None):
		if not self.api_key and self.provider != "Custom":
			frappe.log_error(title="Chatbot AI key is missing")
			return None
		self.current_message = message or ""
		try:
			if self.provider == "OpenAI":
				return self.openai_response(message, conversation_history)
			if self.provider == "Anthropic":
				return self.anthropic_response(message, conversation_history)
			if self.provider == "Google":
				return self.google_response(message, conversation_history)
			if self.provider == "Custom":
				return self.custom_response(message, conversation_history)
		except Exception:
			frappe.log_error(title="Chatbot AI response failed")
		return None

	def build_context(self) -> str:
		try:
			rows = frappe.get_all(
				"WA AI Context",
				filters={"enabled": 1},
				fields=["*"],
				order_by="priority desc",
			)
		except Exception:
			return ""
		parts = []
		account = getattr(self.settings, "whatsapp_account", None)
		lowered = (self.current_message or "").lower()
		for ctx in rows:
			try:
				if not account or ctx.whatsapp_account != account:
					continue
				keywords = [item.strip().lower() for item in (ctx.trigger_keywords or "").split(",") if item.strip()]
				if keywords and not any(word in lowered for word in keywords):
					continue
				if ctx.context_type == "Static Text" and ctx.static_content:
					parts.append(f"[{ctx.title}]\n{ctx.static_content}")
				elif ctx.context_type == "DocType Query":
					data = self.query_doctype(ctx)
					if data:
						parts.append(f"[{ctx.title}]\n{json.dumps(data, separators=(',', ':'), default=str)}")
			except Exception:
				frappe.log_error(title=f"Chatbot AI context failed: {ctx.get('title')}")
		return "\n\n".join(parts)

	def query_doctype(self, ctx):
		target = ctx.query_doctype
		if not target or target in ("User", "DocType", "System Settings", "WA Account", "WA Settings"):
			return None
		filters = ctx.filters or {}
		if isinstance(filters, str):
			filters = json.loads(filters) if filters else {}
		if ctx.user_specific and ctx.phone_field and self.phone_number:
			filters[ctx.phone_field] = ["in", phone_variants(self.phone_number)]
		fields = ["name"]
		if ctx.fields_to_include:
			fields = [item.strip() for item in ctx.fields_to_include.split(",") if item.strip()]
		return frappe.get_all(target, filters=filters, fields=fields, limit=int(ctx.max_results or 10))

	def openai_response(self, message, conversation_history):
		messages = [{"role": "system", "content": self.system_prompt}]
		context = self.build_context()
		if context:
			messages.append({"role": "system", "content": f"Here is relevant information you can use to answer questions:\n{context}"})
		messages.extend(self._history(conversation_history, "assistant"))
		messages.append({"role": "user", "content": message})
		payload = {
			"model": self.model,
			"messages": messages,
			"max_tokens": self.max_tokens,
			"temperature": self.temperature,
		}
		body = _post_json(
			"https://api.openai.com/v1/chat/completions",
			payload,
			{"Authorization": f"Bearer {self.api_key}"},
		)
		choices = (body or {}).get("choices") or []
		if not choices:
			return None
		return ((choices[0].get("message") or {}).get("content")) or None

	def anthropic_response(self, message, conversation_history):
		system = self.system_prompt
		context = self.build_context()
		if context:
			system += f"\n\nHere is relevant information you can use to answer questions:\n{context}"
		messages = self._history(conversation_history, "assistant")
		messages.append({"role": "user", "content": message})
		payload = {"model": self.model, "max_tokens": self.max_tokens, "system": system, "messages": messages}
		body = _post_json(
			"https://api.anthropic.com/v1/messages",
			payload,
			{"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
		)
		content = (body or {}).get("content") or []
		if content and isinstance(content[0], dict):
			return content[0].get("text")
		return None

	def google_response(self, message, conversation_history):
		model = self.model or "gemini-2.0-flash"
		contents = []
		for item in self._history(conversation_history, "model"):
			role = "user" if item["role"] == "user" else "model"
			contents.append({"role": role, "parts": [{"text": item["content"]}]})
		full = message
		context = self.build_context()
		if context:
			full = f"Context:\n{context}\n\nQuestion: {message}"
		contents.append({"role": "user", "parts": [{"text": full}]})
		payload = {
			"system_instruction": {"parts": [{"text": self.system_prompt}]},
			"contents": contents,
			"generationConfig": {"maxOutputTokens": self.max_tokens, "temperature": self.temperature},
		}
		url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
		body = _post_json(url, payload, {})
		candidates = (body or {}).get("candidates") or []
		if not candidates:
			return None
		parts = ((candidates[0].get("content") or {}).get("parts")) or []
		return parts[0].get("text") if parts else None

	def custom_response(self, message, conversation_history):
		"""POST the prompt to the URL stored in AI Model."""
		if not str(self.model or "").startswith("https://"):
			frappe.log_error(title="Custom chatbot AI needs an https URL in AI Model")
			return None
		payload = {
			"message": message,
			"system": self.system_prompt,
			"history": (conversation_history or [])[-self.history_limit :],
		}
		headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
		body = _post_json(self.model, payload, headers)
		if isinstance(body, dict):
			return body.get("message") or body.get("response") or body.get("text")
		return None

	def _history(self, conversation_history, assistant_role: str) -> list[dict]:
		if not self.include_history or not conversation_history:
			return []
		messages = []
		for item in conversation_history[-self.history_limit :]:
			text = (item.get("message") or "")[:200]
			role = "user" if item.get("direction") == "Incoming" else assistant_role
			messages.append({"role": role, "content": text})
		return messages


def phone_variants(phone: str) -> list[str]:
	if not phone:
		return []
	clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
	variants = {phone, clean}
	if clean.startswith("+"):
		variants.add(clean[1:])
	else:
		variants.add("+" + clean)
	digits = clean[1:] if clean.startswith("+") else clean
	if len(digits) > 10:
		variants.add(digits[-10:])
	return list(variants)


def _post_json(url: str, payload: dict, headers: dict):
	data = json.dumps(payload).encode()
	req = request.Request(url, data=data, method="POST")
	req.add_header("Content-Type", "application/json")
	for key, value in headers.items():
		if value:
			req.add_header(key, value)
	try:
		with request.urlopen(req, timeout=30) as response:
			return json.loads(response.read().decode() or "{}")
	except error.HTTPError as exc:
		frappe.log_error(title="Chatbot AI HTTP error", message=exc.read().decode(errors="replace")[:1000])
		return None
	except Exception:
		frappe.log_error(title="Chatbot AI request failed")
		return None
