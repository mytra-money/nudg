# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

from nudg.services.campaign_schedules import end_date_for


class WACampaign(Document):
	def validate(self):
		self._set_account()
		self._set_dates()
		self._load_recipients()
		self._set_status()

	def _set_account(self):
		if not self.campaign:
			frappe.throw(_("Select a campaign."))
		if not frappe.db.exists("UTM Campaign", self.campaign):
			frappe.throw(_("Campaign {0} was not found.").format(self.campaign))
		self.whatsapp_account = frappe.db.get_value("UTM Campaign", self.campaign, "whatsapp_account")

	def _set_dates(self):
		"""End date is calculated the same way as an Email Campaign."""
		if not self.start_date:
			frappe.throw(_("Start Date is required."))
		if not self.trigger_time:
			frappe.throw(_("Trigger Time is required."))
		previous = self.get_doc_before_save()
		start_changed = previous is None or str(getattr(previous, "start_date", "") or "") != str(self.start_date)
		if start_changed and getdate(self.start_date) < getdate(today()):
			frappe.throw(_("Start Date cannot be before the current date."))
		end = end_date_for(self.start_date, self._schedule_days())
		if not end:
			frappe.throw(_("Please set up the Campaign Schedule in the Campaign {0}").format(self.campaign))
		self.end_date = end

	def _schedule_days(self) -> list[int]:
		if not self.campaign or not frappe.db.exists("DocType", "WA Campaign Schedule"):
			return []
		rows = frappe.get_all(
			"WA Campaign Schedule",
			filters={"parent": self.campaign, "parenttype": "UTM Campaign"},
			fields=["send_after_days"],
			limit_page_length=0,
		)
		if not isinstance(rows, list):
			return []
		return [int(row.get("send_after_days") or 0) for row in rows]

	def _load_recipients(self):
		rows = recipient_rows(self.recipient_type, self.recipient)
		if not rows:
			frappe.throw(_("This profile or recipient list has no phone numbers."))
		self.set("recipients", [])
		for row in rows:
			self.append("recipients", row)

	def _set_status(self):
		if self.status == "Cancelled":
			return
		on = getdate(today())
		start = getdate(self.start_date)
		end = getdate(self.end_date) if self.end_date else start
		if on < start:
			self.status = "Scheduled"
		elif on <= end:
			self.status = "In Progress"
		else:
			self.status = "Completed"


def recipient_rows(recipient_type: str | None, recipient: str | None) -> list[dict]:
	"""People from a WhatsApp profile or a recipient list."""
	recipient_type = (recipient_type or "").strip()
	recipient = (recipient or "").strip()
	if recipient_type not in ("WA Profile", "WA Recipient List"):
		frappe.throw(_("Recipient type must be WA Profile or WA Recipient List."))
	if not recipient:
		frappe.throw(_("Select a recipient."))
	if recipient_type == "WA Recipient List":
		return _rows_from_list(recipient)
	return _rows_from_profile(recipient)


def _rows_from_list(list_name: str) -> list[dict]:
	if not frappe.db.exists("WA Recipient List", list_name):
		frappe.throw(_("Recipient List {0} was not found.").format(list_name))
	people = frappe.get_all(
		"WA Recipient",
		filters={"parent": list_name, "parenttype": "WA Recipient List"},
		fields=["mobile_number", "recipient_name", "recipient_data"],
		limit_page_length=0,
	)
	if not isinstance(people, list):
		return []
	return [
		{
			"mobile_number": person.get("mobile_number"),
			"recipient_name": person.get("recipient_name"),
			"recipient_data": person.get("recipient_data"),
		}
		for person in people
		if person.get("mobile_number")
	]


def _rows_from_profile(profile: str) -> list[dict]:
	if not frappe.db.exists("WA Profile", profile):
		frappe.throw(_("Profile {0} was not found.").format(profile))
	row = frappe.db.get_value("WA Profile", profile, ["profile_name", "phone_number"], as_dict=True) or {}
	phone = (row.get("phone_number") or "").strip()
	if not phone:
		frappe.throw(_("Profile {0} has no phone number.").format(profile))
	return [{"mobile_number": phone, "recipient_name": row.get("profile_name") or profile}]


@frappe.whitelist()
def preview_recipients(recipient_type: str | None = None, recipient: str | None = None) -> list[dict]:
	"""Fill the recipient grid when the profile or list changes."""
	frappe.has_permission("WA Campaign", "read", throw=True)
	if not (recipient_type or "").strip() or not (recipient or "").strip():
		return []
	return recipient_rows(recipient_type, recipient)
