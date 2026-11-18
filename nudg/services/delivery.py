# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Close outgoing WhatsApp messages whose send never finished."""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime

# A live send stays inside one request. A Pending row older than this was saved
# and then abandoned, so the inbox must stop showing it as still sending.
STUCK_AFTER_MINUTES = 2
STUCK_ERROR = "Send did not finish. Try sending it again."


def fail_stuck_outgoing() -> int:
	"""Mark abandoned outgoing sends as Failed, or Sent when Meta already accepted them.

	Returns the number of messages updated.
	"""
	if not frappe.db.exists("DocType", "WA Message"):
		return 0

	cutoff = add_to_date(now_datetime(), minutes=-STUCK_AFTER_MINUTES)
	rows = frappe.get_all(
		"WA Message",
		filters={"direction": "Outgoing", "status": "Pending", "creation": ["<", cutoff]},
		fields=["name", "message_id", "error_message"],
		limit_page_length=100,
		ignore_permissions=True,
	)
	updated = 0
	for row in rows:
		accepted = str(row.get("message_id") or "").strip()
		values: dict[str, str] = {"status": "Sent" if accepted else "Failed"}
		if not accepted and not str(row.get("error_message") or "").strip():
			values["error_message"] = STUCK_ERROR
		frappe.db.set_value("WA Message", row.name, values, update_modified=False)
		updated += 1
	return updated
