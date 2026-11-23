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
	"WA Chatbot Session": ("read", "report", "print"),
	"WA Agent Transfer": ("read", "write", "create", "report", "print"),
	"WA Bulk Message": ("read", "report", "print"),
	"WA Campaign": ("read", "report", "print"),
}

# Broadcasts and catalogs are manager work. Agents keep the inbox.
AGENT_LOCKED = (
	"UTM Campaign",
	"WA Catalog",
	"WA Catalog Item",
	"WA Bulk Message",
	"WA Campaign",
	"WA Recipient List",
	"WA Chatbot",
	"WA Keyword Reply",
	"WA Chatbot Flow",
	"WA AI Context",
)

MANAGER_GRANTS = {
	"WA Account": ("read", "write", "create", "report", "print"),
	"UTM Campaign": ("read", "write", "create", "delete", "report", "print"),
	"WA Quick Reply": ("read", "write", "create", "delete", "report", "print"),
	"WA Catalog": ("read", "write", "create", "delete", "report", "print"),
	"WA Catalog Item": ("read", "write", "create", "delete", "report", "print"),
	"WA Bulk Message": ("read", "write", "create", "delete", "submit", "cancel", "report", "print"),
	"WA Campaign": ("read", "write", "create", "delete", "report", "print"),
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


def after_migrate():
	check_frappe_version()
	ensure_role()
	from nudg.services.assignments import migrate_legacy_profile_fields

	migrate_legacy_profile_fields()
	setup_standard_custom_fields()
	_ensure_desk_modules()
	ensure_performance_indexes()
	from nudg.security import backfill_default_accounts

	backfill_default_accounts()


def ensure_performance_indexes() -> None:
	"""Index the columns the inbox, thread, and stuck-message job filter on."""
	specs = (
		("WA Profile", ["phone_number"], "nudg_profile_phone_idx"),
		("WA Profile", ["whatsapp_account"], "nudg_profile_account_idx"),
		("WA Profile", ["modified"], "nudg_profile_modified_idx"),
		("WA Profile", ["whatsapp_account", "modified"], "nudg_profile_account_modified_idx"),
		("WA Catalog Item", ["whatsapp_account"], "nudg_catalog_item_account_idx"),
		("WA Message", ["to"], "nudg_message_to_idx"),
		("WA Message", ["direction"], "nudg_message_direction_idx"),
		("WA Message", ["status"], "nudg_message_status_idx"),
		("WA Message", ["creation"], "nudg_message_creation_idx"),
		("WA Message", ["message_id"], "nudg_message_id_idx"),
		("WA Message", ["to", "creation"], "nudg_message_to_creation_idx"),
		("WA Message", ["direction", "status", "creation"], "nudg_message_stuck_idx"),
	)
	for doctype, fields, index_name in specs:
		try:
			if not frappe.db.table_exists(doctype):
				continue
			if any(not frappe.db.has_column(doctype, field) for field in fields):
				continue
			if _index_covers(doctype, fields):
				continue
			frappe.db.add_index(doctype, fields, index_name)
		except Exception:
			frappe.log_error(title=f"Nudg index {index_name}")


def _index_covers(doctype: str, fields: list[str]) -> bool:
	table = f"tab{doctype}"
	try:
		rows = frappe.db.sql(f"SHOW INDEX FROM `{table}`", as_dict=True)
	except Exception:
		return False
	if not isinstance(rows, list):
		return False
	columns: dict[str, list[tuple[int, str]]] = {}
	for row in rows:
		key = row.get("Key_name") or row.get("key_name")
		column = row.get("Column_name") or row.get("column_name")
		seq = row.get("Seq_in_index") or row.get("seq_in_index") or 0
		if not key or not column:
			continue
		columns.setdefault(key, []).append((int(seq), column))
	for ordered in columns.values():
		names = [name for _, name in sorted(ordered)]
		if names[: len(fields)] == fields:
			return True
	return False


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
			"description": "Set when the site is checked. Connected means the API user can use WA Account. Error means the site or API could not be used.",
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
			"description": "On save, Nudg signs in with this key and checks that WA Account, WA Profile, and WA Message exist on the site.",
		},
		{
			"fieldname": "erp_api_secret",
			"label": "API Secret",
			"fieldtype": "Password",
			"length": 500,
			"insert_after": "erp_api_key",
			"description": "A message lists each check. Fix anything that failed, then save again. Site status becomes Connected or Error.",
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
	"""No custom inbox columns. Assignment, tags, and notes use Frappe core."""
	return []


def setup_standard_custom_fields():
	"""Standard and optional custom fields for Nudg (Zero hard dependency on ERPNext/CRM)."""
	if not getattr(frappe.local, "db", None):
		return

	custom_fields = {}

	# WhatsApp Broadcast extensions for standard UTM Campaign
	if frappe.db.exists("DocType", "UTM Campaign"):
		_drop_custom_fields(
			"UTM Campaign",
			(
				"whatsapp_template",
				"whatsapp_scheduled_at",
				"whatsapp_audience_filter",
				"whatsapp_recipients_section",
				"whatsapp_recipients",
				"whatsapp_status",
				"whatsapp_col_break",
				"whatsapp_sent_count",
				"whatsapp_delivered_count",
				"whatsapp_read_count",
				"whatsapp_failed_count",
				"whatsapp_start_date",
				"whatsapp_recipient_list",
			),
		)
		custom_fields["UTM Campaign"] = [
			{
				"fieldname": "whatsapp_campaign_section",
				"label": "WhatsApp Broadcast",
				"fieldtype": "Section Break",
				"insert_after": "campaign_description",
				"description": "Templates live here. Audience and send dates live on WhatsApp Campaign, which creates the bulk message.",
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
				"fieldname": "whatsapp_last_error",
				"label": "Last Error",
				"fieldtype": "Small Text",
				"read_only": 1,
				"insert_after": "whatsapp_account",
			},
			{
				"fieldname": "whatsapp_schedules_section",
				"label": "WhatsApp Campaign Schedules",
				"fieldtype": "Section Break",
				"insert_after": "whatsapp_last_error",
				"description": "Each row waits Send After days from the WhatsApp Campaign start date, uses a WhatsApp template, and becomes a Bulk WhatsApp Message.",
			},
			{
				"fieldname": "whatsapp_schedules",
				"label": "Schedules",
				"fieldtype": "Table",
				"options": "WA Campaign Schedule",
				"insert_after": "whatsapp_schedules_section",
			},
		]

	if frappe.db.exists("DocType", "WA Account"):
		custom_fields["WA Account"] = [
			{
				"fieldname": "is_default",
				"label": "Default",
				"fieldtype": "Check",
				"insert_after": "status",
				"in_list_view": 1,
				"description": "The first number a user connects is the default. Later numbers stay off until this is checked. Inbox and assignment use the default among the numbers assigned to that user.",
			},
			{
				"fieldname": "two_step_pin",
				"label": "Two-step PIN",
				"fieldtype": "Password",
				"insert_after": "access_token",
				"hidden": 1,
				"description": "Cloud API registration PIN from Embedded Signup. Not shown in the desk.",
			},
			{
				"fieldname": "coexistence",
				"label": "WhatsApp Business App",
				"fieldtype": "Check",
				"insert_after": "two_step_pin",
				"read_only": 1,
				"description": "This number stays on the WhatsApp Business app and on Cloud API. Sends are limited to 20 a second.",
			},
			{
				"fieldname": "platform_type",
				"label": "Platform Type",
				"fieldtype": "Data",
				"insert_after": "coexistence",
				"read_only": 1,
			},
			{
				"fieldname": "coexistence_sync",
				"label": "Business App Sync",
				"fieldtype": "Select",
				"options": "\nSyncing\nSynced\nDeclined\nError",
				"insert_after": "platform_type",
				"read_only": 1,
				"description": "Contacts and the last 6 months of 1:1 chats copy in after connect. Declined means the business did not share history.",
			},
			{
				"fieldname": "coexistence_progress",
				"label": "Business App Sync Progress",
				"fieldtype": "Int",
				"insert_after": "coexistence_sync",
				"read_only": 1,
			},
			{
				"fieldname": "coexistence_error",
				"label": "Business App Sync Error",
				"fieldtype": "Small Text",
				"insert_after": "coexistence_progress",
				"read_only": 1,
			},
			*account_site_fields(),
		]

	if frappe.db.exists("DocType", "User Invitation"):
		custom_fields["User Invitation"] = [
			{
				"fieldname": "nudg_role",
				"label": "Role",
				"fieldtype": "Select",
				"options": "\nWhatsApp User\nWhatsApp Manager",
				"insert_after": "redirect_to_path",
				"depends_on": "eval:doc.app_name=='nudg'",
				"mandatory_depends_on": "eval:doc.app_name=='nudg'",
				"in_list_view": 1,
				"description": "Same as Frappe CRM: WhatsApp Manager also receives WhatsApp User when the invitation is accepted.",
			},
			{
				"fieldname": "nudg_account",
				"label": "WhatsApp Account",
				"fieldtype": "Link",
				"options": "WA Account",
				"insert_after": "nudg_role",
				"depends_on": "eval:doc.app_name=='nudg'",
				"description": "Number granted when the invitation is accepted.",
			},
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
			{
				"fieldname": "client_sync",
				"label": "Client Sync",
				"fieldtype": "Select",
				"options": "\nPending\nSynced\nError",
				"insert_after": "nudg_flow_response",
				"read_only": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
				"description": "Pending until this message is copied to the client site. Synced after that copy succeeds.",
			},
			{
				"fieldname": "client_sync_error",
				"label": "Client Sync Error",
				"fieldtype": "Small Text",
				"insert_after": "client_sync",
				"read_only": 1,
			},
		]

	if frappe.db.exists("DocType", "WA Profile"):
		_drop_custom_fields(
			"WA Profile",
			(
				"consent_status",
				"consent_reason",
				"assignee",
				"assignment_status",
				"priority",
				"tags",
				"last_assigned_on",
				"assignment_source",
				"conversation_status",
				"inbox_section",
				"inbox_col",
			),
		)
		inbox_fields = profile_inbox_fields()
		if inbox_fields:
			custom_fields["WA Profile"] = inbox_fields

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
	ensure_signup_role()


def ensure_signup_role() -> None:
	"""Website sign-up grants WhatsApp Manager.

	On a hosted Nudg site this replaces whatever portal role was there. On a
	self-hosted site that already uses another portal role, such as Customer,
	that role is left in place.
	"""
	if not frappe.db.exists("DocType", "Portal Settings"):
		return
	if not frappe.db.exists("Role", ROLE_MANAGER):
		return
	current = frappe.db.get_single_value("Portal Settings", "default_role") or ""
	if current == ROLE_MANAGER:
		return
	from nudg.desk_access import is_saas_site

	if current and current not in (ROLE, ROLE_MANAGER) and not is_saas_site():
		return
	frappe.db.set_single_value("Portal Settings", "default_role", ROLE_MANAGER)


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
