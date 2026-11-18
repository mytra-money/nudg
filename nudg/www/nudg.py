from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint

from nudg.integrations.whatsapp import adapter

no_cache = 1
safe_render = False


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + quote("/nudg", safe="")
		raise frappe.Redirect

	installed = bool(frappe.db.exists("DocType", "WA Message"))
	if installed and not frappe.has_permission("WA Message", "read"):
		frappe.throw(
			_("You need permission to read WhatsApp Messages. A System Manager can assign the WhatsApp User role."),
			frappe.PermissionError,
		)

	context.boot = get_boot()


def get_boot():
	user_roles = frappe.get_roles(frappe.session.user)
	is_manager = (
		"WhatsApp Manager" in user_roles
		or "System Manager" in user_roles
		or frappe.session.user == "Administrator"
	)
	is_system_manager = "System Manager" in user_roles or frappe.session.user == "Administrator"
	installed = bool(frappe.db.exists("DocType", "WA Message"))
	integration = adapter.get_integration_status()
	if not is_system_manager:
		integration["default_account"] = None

	# ``whatsapp_installed`` stays "the WA Message DocType exists", which the
	# desk shell already reads. ``integration`` is the Phase 1 status contract.
	return {
		"csrf_token": frappe.sessions.get_csrf_token(),
		"user": frappe.session.user,
		"roles": user_roles,
		"is_manager": is_manager,
		"is_system_manager": is_system_manager,
		"sitename": frappe.local.site,
		"site_name": frappe.local.site,
		"socketio_port": cint(frappe.conf.socketio_port),
		"whatsapp_installed": installed,
		"integration": integration,
	}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=True)
def get_context_for_dev():
	"""Boot payload for Vite dev server (CRM/LMS pattern)."""
	if not frappe.conf.developer_mode:
		frappe.throw(_("This method is only meant for developer mode"))
	return get_boot()
