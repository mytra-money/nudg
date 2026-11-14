# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Desk access for WhatsApp roles.

On a SaaS site (Frappe, whatsapp, and nudg only, unless site config says
otherwise) WhatsApp Manager and WhatsApp User have no Desk access. Login
sends them to /nudg.
Administrator and System Manager keep Desk.

On a self-hosted site, Nudg Manager still leaves WhatsApp and Nudg open.
Nudg Agent blocks every Desk module. Profiles are assigned when this app
creates a user, not by rewriting every existing user.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint
from frappe.utils.modules import get_blockable_module_names

PROFILE_MANAGER = "Nudg Manager"
PROFILE_AGENT = "Nudg Agent"
ALLOWED_MANAGER_MODULES = {"WhatsApp", "Nudg"}
ROLE_USER = "WhatsApp User"
ROLE_MANAGER = "WhatsApp Manager"
SAAS_HOME = "nudg"
_WHATSAPP_ROLES = {ROLE_USER, ROLE_MANAGER}
# A hosted Nudg site is Frappe plus the WhatsApp app. ERPNext, LMS, and
# anything else means the customer still uses Desk.
_SAAS_APPS = {"frappe", "whatsapp", "nudg"}


def ensure_module_profiles():
	"""Create the two Module Profile records. Does not update existing users."""
	if not getattr(frappe.local, "db", None):
		return
	if not frappe.db.exists("DocType", "Module Profile"):
		return
	_upsert_profile(PROFILE_MANAGER, _blocked_for_manager())
	_upsert_profile(PROFILE_AGENT, get_blockable_module_names())


def ensure_module_access():
	"""Install/migrate entry point. Profiles, plus the SaaS Desk lock on the two roles."""
	ensure_module_profiles()
	sync_role_desk_access()


def is_saas_site() -> bool:
	"""True on a hosted Nudg site: Frappe, whatsapp, and nudg only.

	``nudg_saas`` in site config wins: 1 locks Desk, 0 leaves it open.
	"""
	conf = getattr(frappe, "conf", None)
	if conf is not None and conf.get("nudg_saas") is not None:
		return bool(cint(conf.get("nudg_saas")))
	try:
		apps = set(frappe.get_installed_apps() or [])
	except Exception:
		return False
	return bool(apps) and apps <= _SAAS_APPS


def user_blocked_from_desk(user: str | None = None) -> bool:
	"""SaaS WhatsApp Manager and WhatsApp User cannot open Desk."""
	if not is_saas_site():
		return False
	user = user or getattr(getattr(frappe, "session", None), "user", None)
	if not user or user in ("Guest", "Administrator"):
		return False
	try:
		roles = set(frappe.get_roles(user))
	except Exception:
		return False
	if "System Manager" in roles:
		return False
	return bool(roles & _WHATSAPP_ROLES)


def extend_bootinfo(bootinfo=None):
	if bootinfo is None:
		return
	bootinfo.nudg_block_desk = 1 if user_blocked_from_desk() else 0


def sync_role_desk_access():
	"""Match Role.desk_access to the site mode, then the users who hold those roles.

	Writes the Role row directly. Role.on_update reloads every linked user and
	stops the whole update when one of those users has already been deleted.
	"""
	if not getattr(frappe.local, "db", None):
		return
	if not frappe.db.exists("DocType", "Role"):
		return
	saas = is_saas_site()
	changed = False
	for role_name in (ROLE_USER, ROLE_MANAGER):
		if not frappe.db.exists("Role", role_name):
			continue
		current_desk, current_home = frappe.db.get_value("Role", role_name, ["desk_access", "home_page"])
		desk = 0 if saas else 1
		if saas:
			home = SAAS_HOME
		elif (current_home or "") == SAAS_HOME:
			home = ""
		else:
			home = current_home or ""
		if cint(current_desk) == desk and (current_home or "") == (home or ""):
			continue
		frappe.db.set_value(
			"Role",
			role_name,
			{"desk_access": desk, "home_page": home},
			update_modified=False,
		)
		changed = True
	_sync_whatsapp_user_types()
	if changed:
		frappe.clear_cache()


def _sync_whatsapp_user_types():
	"""Website User on SaaS, System User when Desk is allowed. Skips missing users."""
	saas = is_saas_site()
	names = frappe.get_all(
		"Has Role",
		filters={"role": ["in", list(_WHATSAPP_ROLES)], "parenttype": "User"},
		pluck="parent",
	)
	for name in sorted(set(names)):
		if name in ("Administrator", "Guest") or not frappe.db.exists("User", name):
			continue
		user = frappe.get_doc("User", name)
		roles = {row.role for row in (user.roles or [])}
		if "System Manager" in roles:
			continue
		before_type = user.user_type
		before_profile = user.module_profile or ""
		user.set_system_user()
		if saas:
			desired = profile_name_for_roles(roles)
			if desired and frappe.db.exists("Module Profile", desired):
				user.module_profile = desired
		if user.user_type == before_type and (user.module_profile or "") == before_profile:
			continue
		user.flags.nudg_profile_set = True
		user.save(ignore_permissions=True)


def profile_name_for_roles(roles) -> str | None:
	"""SaaS blocks Desk for both roles. Self-hosted managers keep two modules."""
	roles = set(roles or [])
	if "System Manager" in roles:
		return None
	if is_saas_site():
		if roles & _WHATSAPP_ROLES:
			return PROFILE_AGENT
		return None
	if ROLE_MANAGER in roles:
		return PROFILE_MANAGER
	if ROLE_USER in roles:
		return PROFILE_AGENT
	return None


def assign_module_profile(doc, method=None):
	"""Set module_profile on a newly created user. One user, no site-wide pass."""
	if not getattr(doc, "name", None) or doc.name in ("Administrator", "Guest"):
		return
	if doc.flags.get("nudg_profile_set"):
		return
	roles = {row.role for row in (doc.roles or [])}
	desired = profile_name_for_roles(roles)
	if not desired or (doc.module_profile or "") == desired:
		return
	if not frappe.db.exists("Module Profile", desired):
		return
	doc.module_profile = desired
	doc.flags.nudg_profile_set = True
	doc.save(ignore_permissions=True)


def _blocked_for_manager() -> list[str]:
	return [name for name in get_blockable_module_names() if name not in ALLOWED_MANAGER_MODULES]


def _upsert_profile(name: str, blocked: list[str]):
	blocked = sorted({module for module in blocked if module})
	if frappe.db.exists("Module Profile", name):
		current = sorted(
			frappe.get_all(
				"Block Module",
				filters={"parent": name, "parenttype": "Module Profile"},
				pluck="module",
			)
		)
		if current == blocked:
			return
		doc = frappe.get_doc("Module Profile", name)
	else:
		doc = frappe.new_doc("Module Profile")
		doc.module_profile_name = name
	doc.set("block_modules", [])
	for module in blocked:
		doc.append("block_modules", {"module": module})
	doc.save(ignore_permissions=True)
