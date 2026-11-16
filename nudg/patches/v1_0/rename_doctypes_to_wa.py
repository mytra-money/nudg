"""Rename Nudg DocTypes to the Frappe WhatsApp names before model sync.

Frappe WhatsApp uses a short ``WA`` prefix, as in ``WA Profile`` and
``WA Message``. This runs before model sync so an existing site keeps its
tables and records under the names now stored in the DocType JSON. A fresh
install has neither name yet, and a site that already migrated is skipped.
"""

import frappe

# Longer names first so a child DocType is renamed before a shorter name
# that shares its prefix.
RENAMES = (
	("WhatsApp Campaign Recipient", "WA Campaign Recipient"),
	("WhatsApp Automation Rule", "WA Automation Rule"),
	("WhatsApp Automation Run", "WA Automation Run"),
	("WhatsApp Signup Settings", "WA Signup Settings"),
	("WhatsApp Catalog Item", "WA Catalog Item"),
	("WhatsApp Quick Reply", "WA Quick Reply"),
	("WhatsApp Catalog", "WA Catalog"),
	("Nudg Conversation", "WA Conversation"),
	# A connected Frappe site, not a WhatsApp document, so it does not take the WA prefix.
	("WA ERPNext Site", "Connected Site"),
	("ERPNext Site", "Connected Site"),
)


def execute():
	for old, new in RENAMES:
		_rename_doctype(old, new)


def _rename_doctype(old, new):
	if frappe.db.exists("DocType", new):
		return
	if not frappe.db.exists("DocType", old):
		return
	frappe.rename_doc("DocType", old, new, force=True, show_alert=False, rebuild_search=False)
