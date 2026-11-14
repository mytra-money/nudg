# Copyright (c) 2026, NUDG and contributors
# For license information, please see license.txt

"""Module Profiles for WhatsApp roles.

NUDG Manager blocks every Desk module except WhatsApp and NUDG.
NUDG Agent blocks every Desk module. Profiles are created once. They are
assigned when this app creates a user, not by rewriting every existing user.
Administrator and System Manager are left unchanged.
"""

from __future__ import annotations

import frappe
from frappe.utils.modules import get_blockable_module_names

PROFILE_MANAGER = "NUDG Manager"
PROFILE_AGENT = "NUDG Agent"
ALLOWED_MANAGER_MODULES = {"WhatsApp", "NUDG"}
ROLE_USER = "WhatsApp User"
ROLE_MANAGER = "WhatsApp Manager"


def ensure_module_profiles():
	"""Create the two Module Profile records. Does not update existing users."""
	if not getattr(frappe.local, "db", None):
		return
	if not frappe.db.exists("DocType", "Module Profile"):
		return
	_upsert_profile(PROFILE_MANAGER, _blocked_for_manager())
	_upsert_profile(PROFILE_AGENT, get_blockable_module_names())


def ensure_module_access():
	"""Install/migrate entry point. Profiles only; never a site-wide user update."""
	ensure_module_profiles()


def profile_name_for_roles(roles) -> str | None:
	"""WhatsApp Manager wins. A plain WhatsApp User gets the agent profile."""
	roles = set(roles or [])
	if "System Manager" in roles:
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
