from urllib.parse import quote

import frappe
from frappe import _

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

	user_roles = frappe.get_roles(frappe.session.user)
	is_manager = "WhatsApp Manager" in user_roles or "System Manager" in user_roles or frappe.session.user == "Administrator"

	# ``whatsapp_installed`` stays "the WA Message DocType exists", which the
	# desk shell already reads. ``integration`` is the Phase 1 status contract.
	context.boot = {
		"csrf_token": frappe.sessions.get_csrf_token(),
		"user": frappe.session.user,
		"roles": user_roles,
		"is_manager": is_manager,
		"sitename": frappe.local.site,
		"whatsapp_installed": installed,
		"integration": adapter.get_integration_status(),
	}
