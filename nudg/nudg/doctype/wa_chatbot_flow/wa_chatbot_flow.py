# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


class WAChatbotFlow(Document):
	def validate(self):
		if not self.whatsapp_account:
			frappe.throw(_("Select the WhatsApp account this flow belongs to."))
		self.validate_steps()
		self.validate_completion_action()

	def validate_steps(self):
		if not self.steps:
			frappe.throw(_("Add at least one step."))
		names = []
		for step in self.steps:
			if step.step_name in names:
				frappe.throw(_("Duplicate step name: {0}").format(step.step_name))
			names.append(step.step_name)
			if step.conditional_next:
				try:
					parsed = json.loads(step.conditional_next) if isinstance(step.conditional_next, str) else step.conditional_next
				except json.JSONDecodeError:
					frappe.throw(_("Conditional next on step {0} must be JSON.").format(step.step_name))
				else:
					if not isinstance(parsed, dict):
						frappe.throw(_("Conditional next on step {0} must be a JSON object.").format(step.step_name))
			if step.input_type == "Button" and step.message_type != "Script":
				if not step.buttons or step.buttons in ("{}", "[]", ""):
					frappe.throw(_("Add buttons for step {0}.").format(step.step_name))
				try:
					buttons = json.loads(step.buttons) if isinstance(step.buttons, str) else step.buttons
				except json.JSONDecodeError:
					frappe.throw(_("Buttons on step {0} must be JSON.").format(step.step_name))
				else:
					if not isinstance(buttons, list) or not buttons:
						frappe.throw(_("Buttons on step {0} must be a non-empty array.").format(step.step_name))
		for step in self.steps:
			if step.next_step and step.next_step not in names:
				frappe.throw(_("Step {0} points at missing step {1}.").format(step.step_name, step.next_step))
			if step.conditional_next:
				parsed = json.loads(step.conditional_next) if isinstance(step.conditional_next, str) else step.conditional_next
				for target in parsed.values():
					if target and target not in names:
						frappe.throw(_("Step {0} points at missing step {1}.").format(step.step_name, target))

	def validate_completion_action(self):
		if self.on_complete_action == "Create Document":
			if not self.create_doctype or not self.field_mapping:
				frappe.throw(_("Create Document needs a DocType and a field mapping."))
			try:
				parsed = json.loads(self.field_mapping) if isinstance(self.field_mapping, str) else self.field_mapping
			except json.JSONDecodeError:
				frappe.throw(_("Field mapping must be JSON."))
			if not isinstance(parsed, dict):
				frappe.throw(_("Field mapping must be a JSON object."))
		elif self.on_complete_action == "Call API" and not self.api_endpoint:
			frappe.throw(_("Enter the API endpoint."))
		elif self.on_complete_action == "Run Script" and not self.custom_script:
			frappe.throw(_("Enter the completion script."))
