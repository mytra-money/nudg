# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Nudg invitations follow Frappe CRM.

CRM stores one role on the invitation. Accepting it grants that role and every
role beneath it: a Sales Manager also becomes a Sales User. A WhatsApp Manager
also becomes a WhatsApp User. A WhatsApp User receives only that role.
"""

from __future__ import annotations

import frappe
from frappe import _

from nudg.security import ensure_account_user_permission

WHATSAPP_USER = "WhatsApp User"
WHATSAPP_MANAGER = "WhatsApp Manager"


def prepare_nudg_invitation(doc, method=None) -> None:
	"""Keep a Nudg invitation to one role, and send the person to /nudg."""
	if getattr(doc, "app_name", None) != "nudg":
		return
	role = _selected_role(doc)
	if role not in (WHATSAPP_USER, WHATSAPP_MANAGER):
		frappe.throw(_("Choose WhatsApp Manager or WhatsApp User."))
	doc.nudg_role = role
	doc.set("roles", [])
	doc.append("roles", {"role": role})
	if not (doc.get("redirect_to_path") or "").strip():
		doc.redirect_to_path = "/nudg"


def after_accept(invitation, user, user_inserted=False) -> None:
	assign_invited_roles(user, invitation)
	account = (invitation.get("nudg_account") or "").strip()
	if account and frappe.db.exists("WA Account", account):
		ensure_account_user_permission(account, user.name)
	_apply_module_profile(user)
	user.flags.nudg_profile_set = True
	user.save(ignore_permissions=True)


def assign_invited_roles(user, invitation) -> None:
	"""Grant the invited role and, for a manager, the user role under it."""
	role = _selected_role(invitation)
	if role == WHATSAPP_MANAGER:
		user.append_roles(WHATSAPP_MANAGER, WHATSAPP_USER)
	elif role == WHATSAPP_USER:
		user.append_roles(WHATSAPP_USER)


def _role_of(row) -> str:
	if isinstance(row, dict):
		return row.get("role") or ""
	return getattr(row, "role", None) or ""


def _selected_role(invitation) -> str:
	named = (invitation.get("nudg_role") or "").strip()
	if named in (WHATSAPP_USER, WHATSAPP_MANAGER):
		return named
	child_roles = [_role_of(row) for row in (invitation.get("roles") or [])]
	child_roles = [role for role in child_roles if role]
	if WHATSAPP_MANAGER in child_roles:
		return WHATSAPP_MANAGER
	if WHATSAPP_USER in child_roles:
		return WHATSAPP_USER
	return named


def _apply_module_profile(user) -> None:
	from nudg.desk_access import profile_name_for_roles

	roles = {row.role for row in (user.roles or [])}
	profile = profile_name_for_roles(roles)
	if not profile or (user.module_profile or "") == profile:
		return
	if not frappe.db.exists("Module Profile", profile):
		return
	user.module_profile = profile
	user.flags.nudg_profile_set = True
