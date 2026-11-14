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
	"WhatsApp Catalog": ("read", "report", "print"),
	"WhatsApp Catalog Item": ("read", "report", "print"),
	"WhatsApp Quick Reply": ("read", "write", "create", "report", "print"),
	"Nudg Conversation": ("read", "write", "create", "report", "print"),
	"UTM Campaign": ("read", "report", "print"),
	"WhatsApp Automation Rule": ("read", "report", "print"),
	"WhatsApp Automation Run": ("read", "report", "print"),
}

# Broadcasts, automation, and catalogs are manager work. Agents keep the inbox.
AGENT_LOCKED = (
	"UTM Campaign",
	"WhatsApp Automation Rule",
	"WhatsApp Catalog",
	"WhatsApp Catalog Item",
)

MANAGER_GRANTS = {
	"WA Account": ("read", "write", "create", "report", "print"),
	"Nudg Conversation": ("read", "write", "create", "delete", "report", "print"),
	"UTM Campaign": ("read", "write", "create", "delete", "report", "print"),
	"WhatsApp Automation Rule": ("read", "write", "create", "delete", "report", "print"),
	"WhatsApp Automation Run": ("read", "write", "report", "print"),
	"WhatsApp Quick Reply": ("read", "write", "create", "delete", "report", "print"),
	"WhatsApp Catalog": ("read", "write", "create", "delete", "report", "print"),
	"WhatsApp Catalog Item": ("read", "write", "create", "delete", "report", "print"),
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


def after_migrate():
	check_frappe_version()
	ensure_role()
	setup_standard_custom_fields()
	_ensure_desk_modules()


def _ensure_desk_modules():
	from nudg.desk_access import ensure_module_access

	ensure_module_access()


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
				"options": "WhatsApp Campaign Recipient",
				"insert_after": "whatsapp_recipients_section",
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
		]

	if frappe.db.exists("DocType", "WA Profile"):
		custom_fields["WA Profile"] = [
			{
				"fieldname": "consent_status",
				"label": "Consent Status",
				"fieldtype": "Select",
				"options": "\nOpted-In\nOpted-Out\nPending",
				"insert_after": "status",
				"description": "STOP opts the customer out of broadcasts. A blank value still allows sending.",
			},
			{
				"fieldname": "consent_reason",
				"label": "Consent Reason",
				"fieldtype": "Small Text",
				"insert_after": "consent_status",
			},
		]

	# Optional ERPNext Item integration for self-hosted instances
	if frappe.db.exists("DocType", "WhatsApp Catalog Item") and frappe.db.exists("DocType", "Item"):
		custom_fields["WhatsApp Catalog Item"] = [
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
