"""Catalog bridge for a future Meta Commerce sync.

Phase 2 stores catalogs in desk DocTypes only. Meta Graph calls are not made
here. Sync status is written onto WhatsApp Catalog so the UI never invents it.
"""

from __future__ import annotations

import frappe


def sync_catalog(catalog_name: str) -> dict:
	"""Mark a catalog Pending then Error with a clear unavailable message.

	Replace the body of this function when Meta Commerce sync is implemented.
	"""
	if not frappe.db.exists("WhatsApp Catalog", catalog_name):
		frappe.throw(frappe._("Catalog {0} does not exist.").format(catalog_name), frappe.DoesNotExistError)

	doc = frappe.get_doc("WhatsApp Catalog", catalog_name)
	frappe.has_permission("WhatsApp Catalog", "write", doc=doc, throw=True)
	doc.sync_status = "Pending"
	doc.sync_error = None
	doc.save()

	doc.sync_status = "Error"
	doc.sync_error = (
		"Meta Commerce Catalog sync is not enabled in this build. "
		"Catalog data is stored on this site only."
	)
	doc.save()
	frappe.db.commit()
	return {
		"name": doc.name,
		"sync_status": doc.sync_status,
		"sync_error": doc.sync_error,
		"meta_catalog_id": doc.meta_catalog_id,
	}
