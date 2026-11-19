"""Idempotent role setup for Nudg.

``after_install`` and ``after_migrate`` both call ``ensure_role``. Running
either one again does not delete roles, Custom DocPerm rows, or documents.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

ROLE = "WhatsApp User"
ROLE_MANAGER = "WhatsApp Manager"

GRANTS = {
	"WA Message": ("read", "write", "create", "report", "print", "email"),
	"WA Profile": ("read", "write", "create", "report"),
	"WA Template": ("read", "write", "create", "report"),
}

DESK_GRANTS = {
	"WA Catalog": ("read", "report", "print"),
	"WA Catalog Item": ("read", "report", "print"),
	"WA Quick Reply": ("read", "write", "create", "report", "print"),
	"UTM Campaign": ("read", "report", "print"),
	"WA Automation Rule": ("read", "report", "print"),
	"WA Automation Run": ("read", "report", "print"),
	"WA Chatbot Session": ("read", "report", "print"),
	"WA Agent Transfer": ("read", "write", "create", "report", "print"),
	"WA Bulk Message": ("read", "report", "print"),
}

# Broadcasts, automation, and catalogs are manager work. Agents keep the inbox.
AGENT_LOCKED = (
	"UTM Campaign",
	"WA Automation Rule",
	"WA Catalog",
	"WA Catalog Item",
	"WA Bulk Message",
	"WA Recipient List",
	"WA Chatbot",
	"WA Keyword Reply",
	"WA Chatbot Flow",
	"WA AI Context",
)

MANAGER_GRANTS = {
	"WA Account": ("read", "write", "create", "report", "print"),
	"UTM Campaign": ("read", "write", "create", "delete", "report", "print"),
	"WA Automation Rule": ("read", "write", "create", "delete", "report", "print"),
	"WA Automation Run": ("read", "write", "report", "print"),
	"WA Quick Reply": ("read", "write", "create", "delete", "report", "print"),
	"WA Catalog": ("read", "write", "create", "delete", "report", "print"),
	"WA Catalog Item": ("read", "write", "create", "delete", "report", "print"),
	"WA Bulk Message": ("read", "write", "create", "delete", "submit", "cancel", "report", "print"),
	"WA Recipient List": ("read", "write", "create", "delete", "report", "print"),
	"WA Chatbot": ("read", "write", "create", "report", "print"),
	"WA Keyword Reply": ("read", "write", "create", "delete", "report", "print"),
	"WA Chatbot Flow": ("read", "write", "create", "delete", "report", "print"),
	"WA Chatbot Session": ("read", "write", "delete", "report", "print"),
	"WA Agent Transfer": ("read", "write", "create", "delete", "report", "print"),
	"WA AI Context": ("read", "write", "create", "delete", "report", "print"),
}


def check_frappe_version():
	"""Enforce Frappe Framework v16 or newer."""
	version = getattr(frappe, "__version__", "")
	if version:
		parts = version.split(".")
		if parts[0].isdigit():
			major = int(parts[0])
			if major < 16:
				frappe.throw(
					frappe._("Nudg requires Frappe Framework version 16.0 or newer. Detected version: {0}").format(version),
					frappe.ValidationError,
				)


def after_install():
	check_frappe_version()
	ensure_role()
	setup_standard_custom_fields()
	_ensure_desk_modules()
	_ensure_facebook_login()


def after_migrate():
	check_frappe_version()
	ensure_role()
	setup_standard_custom_fields()
	_ensure_desk_modules()
	_ensure_facebook_login()


def _ensure_facebook_login():
	from nudg.integrations.facebook_login import ensure_facebook_login

	ensure_facebook_login(seed=True)


def _ensure_desk_modules():
	from nudg.desk_access import ensure_module_access

	ensure_module_access()


def account_site_fields() -> list[dict]:
	"""Connected ERPNext site, stored on the WhatsApp account."""
	return [
		{
			"fieldname": "connected_site_tab",
			"label": "Connected Site",
			"fieldtype": "Tab Break",
			"insert_after": "append_actions",
		},
		{
			"fieldname": "erp_site_name",
			"label": "Site Name",
			"fieldtype": "Data",
			"insert_after": "connected_site_tab",
			"in_list_view": 1,
		},
		{
			"fieldname": "erp_status",
			"label": "Site Status",
			"fieldtype": "Select",
			"options": "Pending\nConnected\nDisabled\nError",
			"default": "Pending",
			"insert_after": "erp_site_name",
			"in_list_view": 1,
		},
		{
			"fieldname": "erp_site_url",
			"label": "Site URL",
			"fieldtype": "Data",
			"length": 300,
			"insert_after": "erp_status",
		},
		{
			"fieldname": "erp_remote_user",
			"label": "Remote User",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "erp_site_url",
		},
		{
			"fieldname": "erp_credentials_col",
			"fieldtype": "Column Break",
			"insert_after": "erp_remote_user",
		},
		{
			"fieldname": "erp_api_key",
			"label": "API Key",
			"fieldtype": "Password",
			"length": 500,
			"insert_after": "erp_credentials_col",
		},
		{
			"fieldname": "erp_api_secret",
			"label": "API Secret",
			"fieldtype": "Password",
			"length": 500,
			"insert_after": "erp_api_key",
		},
		{
			"fieldname": "erp_inbound_secret",
			"label": "Inbound Secret",
			"fieldtype": "Password",
			"read_only": 1,
			"insert_after": "erp_api_secret",
			"description": "Nudge generates this and installs it as the ERPNext webhook secret.",
		},
		{
			"fieldname": "erp_last_error",
			"label": "Last Error",
			"fieldtype": "Small Text",
			"read_only": 1,
			"insert_after": "erp_inbound_secret",
		},
	]


def profile_inbox_fields() -> list[dict]:
	"""Assignment, tags, and cached inbox status live on the WhatsApp profile."""
	return [
		{
			"fieldname": "inbox_section",
			"label": "Assignment",
			"fieldtype": "Section Break",
			"insert_after": "wa_id",
		},
		{
			"fieldname": "assignee",
			"label": "Assignee",
			"fieldtype": "Link",
			"options": "User",
			"insert_after": "inbox_section",
			"in_list_view": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "assignment_status",
			"label": "Assignment Status",
			"fieldtype": "Select",
			"options": "Unassigned\nAssigned\nClosed",
			"default": "Unassigned",
			"insert_after": "assignee",
			"in_list_view": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "priority",
			"label": "Priority",
			"fieldtype": "Select",
			"options": "Low\nMedium\nHigh",
			"default": "Medium",
			"insert_after": "assignment_status",
		},
		{
			"fieldname": "tags",
			"label": "Tags",
			"fieldtype": "Data",
			"insert_after": "priority",
			"in_list_view": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "inbox_col",
			"fieldtype": "Column Break",
			"insert_after": "tags",
		},
		{
			"fieldname": "last_assigned_on",
			"label": "Last Assigned On",
			"fieldtype": "Datetime",
			"read_only": 1,
			"insert_after": "inbox_col",
		},
		{
			"fieldname": "assignment_source",
			"label": "Assignment Source",
			"fieldtype": "Select",
			"options": "\nManual\nAssignment Rule\nRound Robin",
			"read_only": 1,
			"insert_after": "last_assigned_on",
		},
		{
			"fieldname": "conversation_status",
			"label": "Inbox Status",
			"fieldtype": "Select",
			"options": "template_only\nneeds_reply\nwindow_open\nfailed\nblocked\nclosed",
			"insert_after": "assignment_source",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"read_only": 1,
			"description": "Cached from the latest WA Message and the 24-hour window. The inbox recomputes it.",
		},
	]


def setup_standard_custom_fields():
	"""Standard and optional custom fields for Nudg (Zero hard dependency on ERPNext/CRM)."""
	if not getattr(frappe.local, "db", None):
		return

	custom_fields = {}

	# WhatsApp Broadcast extensions for standard UTM Campaign
	if frappe.db.exists("DocType", "UTM Campaign"):
		custom_fields["UTM Campaign"] = [
			{
				"fieldname": "whatsapp_campaign_section",
				"label": "WhatsApp Broadcast",
				"fieldtype": "Section Break",
				"insert_after": "campaign_description",
			},
			{
				"fieldname": "whatsapp_account",
				"label": "WhatsApp Account",
				"fieldtype": "Link",
				"options": "WA Account",
				"insert_after": "whatsapp_campaign_section",
				"in_list_view": 1,
				"in_standard_filter": 1,
			},
			{
				"fieldname": "whatsapp_template",
				"label": "WhatsApp Template",
				"fieldtype": "Link",
				"options": "WA Template",
				"insert_after": "whatsapp_account",
				"in_list_view": 1,
			},
			{
				"fieldname": "whatsapp_status",
				"label": "WhatsApp Status",
				"fieldtype": "Select",
				"options": "Draft\nScheduled\nRunning\nCompleted\nFailed\nCancelled",
				"default": "Draft",
				"insert_after": "whatsapp_template",
				"in_list_view": 1,
			},
			{
				"fieldname": "whatsapp_scheduled_at",
				"label": "Scheduled At",
				"fieldtype": "Datetime",
				"insert_after": "whatsapp_status",
			},
			{
				"fieldname": "whatsapp_audience_filter",
				"label": "Audience Filter",
				"fieldtype": "Code",
				"options": "JSON",
				"insert_after": "whatsapp_scheduled_at",
			},
			{
				"fieldname": "whatsapp_col_break",
				"fieldtype": "Column Break",
				"insert_after": "whatsapp_audience_filter",
			},
			{
				"fieldname": "whatsapp_sent_count",
				"label": "Sent Count",
				"fieldtype": "Int",
				"default": "0",
				"read_only": 1,
				"insert_after": "whatsapp_col_break",
			},
			{
				"fieldname": "whatsapp_delivered_count",
				"label": "Delivered Count",
				"fieldtype": "Int",
				"default": "0",
				"read_only": 1,
				"insert_after": "whatsapp_sent_count",
			},
			{
				"fieldname": "whatsapp_read_count",
				"label": "Read Count",
				"fieldtype": "Int",
				"default": "0",
				"read_only": 1,
				"insert_after": "whatsapp_delivered_count",
			},
			{
				"fieldname": "whatsapp_failed_count",
				"label": "Failed Count",
				"fieldtype": "Int",
				"default": "0",
				"read_only": 1,
				"insert_after": "whatsapp_read_count",
			},
			{
				"fieldname": "whatsapp_last_error",
				"label": "Last Error",
				"fieldtype": "Small Text",
				"read_only": 1,
				"insert_after": "whatsapp_failed_count",
			},
			{
				"fieldname": "whatsapp_recipients_section",
				"label": "WhatsApp Recipients",
				"fieldtype": "Section Break",
				"insert_after": "whatsapp_last_error",
			},
			{
				"fieldname": "whatsapp_recipients",
				"label": "Recipients",
				"fieldtype": "Table",
				"options": "WA Campaign Recipient",
				"insert_after": "whatsapp_recipients_section",
			},
			{
				"fieldname": "whatsapp_schedules_section",
				"label": "WhatsApp Campaign Schedules",
				"fieldtype": "Section Break",
				"insert_after": "whatsapp_recipients",
				"description": "Same timing as an Email Campaign: each row waits Send After days from the start date, uses a WhatsApp template, and creates a Bulk WhatsApp Message.",
			},
			{
				"fieldname": "whatsapp_start_date",
				"label": "Start Date",
				"fieldtype": "Date",
				"insert_after": "whatsapp_schedules_section",
			},
			{
				"fieldname": "whatsapp_recipient_list",
				"label": "Default Recipient List",
				"fieldtype": "Link",
				"options": "WA Recipient List",
				"insert_after": "whatsapp_start_date",
			},
			{
				"fieldname": "whatsapp_schedules",
				"label": "Schedules",
				"fieldtype": "Table",
				"options": "WA Campaign Schedule",
				"insert_after": "whatsapp_recipient_list",
			},
		]

	if frappe.db.exists("DocType", "WA Account"):
		custom_fields["WA Account"] = [
			{
				"fieldname": "two_step_pin",
				"label": "Two-step PIN",
				"fieldtype": "Password",
				"insert_after": "access_token",
				"hidden": 1,
				"description": "Cloud API registration PIN from Embedded Signup. Not shown in the desk.",
			},
			*account_site_fields(),
		]

	if frappe.db.exists("DocType", "WA Message"):
		custom_fields["WA Message"] = [
			{
				"fieldname": "bulk_message",
				"label": "Bulk Message",
				"fieldtype": "Link",
				"options": "WA Bulk Message",
				"insert_after": "reference_docname",
				"read_only": 1,
			},
			{
				"fieldname": "nudg_flow_response",
				"label": "Flow Response",
				"fieldtype": "Code",
				"options": "JSON",
				"insert_after": "bulk_message",
				"hidden": 1,
				"read_only": 1,
			},
		]

	if frappe.db.exists("DocType", "WA Profile"):
		_drop_custom_fields("WA Profile", ("consent_status", "consent_reason"))
		custom_fields["WA Profile"] = profile_inbox_fields()

	# Optional ERPNext Item integration for self-hosted instances
	if frappe.db.exists("DocType", "WA Catalog Item") and frappe.db.exists("DocType", "Item"):
		custom_fields["WA Catalog Item"] = [
			{
				"fieldname": "erpnext_item",
				"label": "ERPNext Item (Optional)",
				"fieldtype": "Link",
				"options": "Item",
				"insert_after": "catalog",
				"description": "Optional: Fetch item name, price, and image from ERPNext Item.",
			}
		]

	if custom_fields:
		try:
			from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
			create_custom_fields(custom_fields, ignore_validate=True)
			for dt in custom_fields.keys():
				frappe.clear_cache(doctype=dt)
		except Exception:
			frappe.log_error(title="Nudg setup_standard_custom_fields error")


def _drop_custom_fields(doctype: str, fieldnames: tuple[str, ...]) -> None:
	"""Remove custom fields that should no longer appear on the form."""
	removed = False
	for fieldname in fieldnames:
		name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname})
		if not name:
			continue
		frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
		removed = True
	if removed:
		frappe.clear_cache(doctype=doctype)


def ensure_role():
	for r in (ROLE, ROLE_MANAGER):
		if not frappe.db.exists("Role", r):
			role = frappe.new_doc("Role")
			role.role_name = r
			role.desk_access = 1
			role.insert(ignore_permissions=True)

	from nudg.desk_access import sync_role_desk_access

	sync_role_desk_access()

	_apply_grants(GRANTS, role_name=ROLE, require_whatsapp=True)
	_apply_grants(DESK_GRANTS, role_name=ROLE, require_whatsapp=False)
	_apply_grants(GRANTS, role_name=ROLE_MANAGER, require_whatsapp=True)
	_apply_grants(MANAGER_GRANTS, role_name=ROLE_MANAGER, require_whatsapp=False)
	_lock_agent_manager_only()


def _apply_grants(grants: dict, role_name: str = ROLE, require_whatsapp: bool = False):
	if require_whatsapp and "whatsapp" not in frappe.get_installed_apps():
		return
	for doctype, properties in grants.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		perm_name = frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": role_name, "permlevel": 0})
		if not perm_name:
			add_permission(doctype, role_name, 0)
			perm_name = frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": role_name, "permlevel": 0})
		if not perm_name:
			continue
		updates = {}
		current_vals = frappe.db.get_value("Custom DocPerm", perm_name, ["read", "write", "create", "delete", "report", "print", "email", "export", "share"], as_dict=True) or {}
		for prop in properties:
			if current_vals.get(prop) != 1:
				updates[prop] = 1
		for prop in ("delete", "export", "share"):
			if prop not in properties and current_vals.get(prop) != 0:
				updates[prop] = 0
		if updates:
			frappe.db.set_value("Custom DocPerm", perm_name, updates, update_modified=False)


def _lock_agent_manager_only():
	"""Clear agent create/write that an earlier install may have granted."""
	for doctype in AGENT_LOCKED:
		if not frappe.db.exists("DocType", doctype):
			continue
		perm_name = frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": ROLE, "permlevel": 0})
		if not perm_name:
			add_permission(doctype, ROLE, 0)
			perm_name = frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": ROLE, "permlevel": 0})
		if not perm_name:
			continue
		frappe.db.set_value(
			"Custom DocPerm",
			perm_name,
			{
				"read": 1,
				"write": 0,
				"create": 0,
				"delete": 0,
				"export": 0,
				"share": 0,
				"report": 1,
				"print": 1,
			},
			update_modified=False,
		)
