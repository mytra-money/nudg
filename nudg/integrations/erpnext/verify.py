# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Check a client site before Nudg stores chats there."""

from __future__ import annotations

from nudg.integrations.erpnext.client import ERPNextClientError

# The official WhatsApp app owns these. Chats are stored with them.
_REQUIRED = (
	("WA Account", ("read", "create")),
	("WA Profile", ("read", "create")),
	("WA Message", ("read", "create", "write", "submit")),
)


def verify_remote_site(client) -> dict:
	"""Sign in, then confirm the WhatsApp DocTypes and this user's permissions.

	``status`` is Connected only when every check passes. A site that cannot be
	reached, or an API user that cannot be used, is Error.
	"""
	try:
		remote_user = client.get_logged_user()
	except ERPNextClientError as exc:
		detail = _sign_in_detail(exc, client)
		return _result(
			ok=False,
			status="Error",
			remote_user="",
			checks=[{"name": "Sign in", "ok": False, "detail": detail}],
		)

	checks = [{"name": "Sign in", "ok": True, "detail": f"Signed in as {remote_user}."}]
	roles = _roles(client, remote_user)
	if remote_user != "Administrator" and not roles:
		checks.append(
			{
				"name": "Permissions",
				"ok": False,
				"detail": (
					f"Nudg could not read roles for {remote_user}. "
					"Use an API key for a user that can open its own User document."
				),
			}
		)
		return _result(ok=False, status="Error", remote_user=remote_user, checks=checks)

	role_set = set(roles)
	if remote_user == "Administrator":
		role_set.add("Administrator")

	for doctype, needed in _REQUIRED:
		meta, problem = _doctype_meta(client, doctype)
		if problem:
			checks.append({"name": doctype, "ok": False, "detail": problem})
			continue
		checks.append({"name": doctype, "ok": True, "detail": f"{doctype} is installed on that site."})
		missing = missing_permissions(meta or {}, role_set, needed)
		if missing:
			checks.append(
				{
					"name": f"{doctype} permissions",
					"ok": False,
					"detail": (
						f"{remote_user} cannot {', '.join(missing)} {doctype}. "
						f"Grant {', '.join(missing)} on {doctype} for one of this user's roles."
					),
				}
			)
		else:
			checks.append(
				{
					"name": f"{doctype} permissions",
					"ok": True,
					"detail": f"{remote_user} can use {doctype}.",
				}
			)

	ok = all(check["ok"] for check in checks)
	return _result(
		ok=ok,
		status="Connected" if ok else "Error",
		remote_user=remote_user,
		checks=checks,
	)


def missing_permissions(meta: dict, roles: set[str], needed: tuple[str, ...]) -> list[str]:
	"""Permission types in ``needed`` that none of ``roles`` grant at level 0."""
	if "Administrator" in roles:
		return []
	submittable = bool(meta.get("is_submittable"))
	rows = [row for row in (meta.get("permissions") or []) if not row.get("permlevel")]
	missing = []
	for perm in needed:
		if perm == "submit" and not submittable:
			continue
		if any(row.get("role") in roles and int(row.get(perm) or 0) for row in rows if isinstance(row, dict)):
			continue
		missing.append(perm)
	return missing


def _roles(client, remote_user: str) -> list[str]:
	if remote_user == "Administrator":
		return ["Administrator"]
	try:
		result = client.call_method("frappe.core.doctype.user.user.get_current_user_roles")
	except ERPNextClientError:
		result = None
	roles = _message_list(result)
	if roles:
		return roles
	try:
		user = client.get_resource("User", remote_user)
	except ERPNextClientError:
		return []
	if not isinstance(user, dict):
		return []
	found = []
	for row in user.get("roles") or []:
		if isinstance(row, dict) and row.get("role"):
			found.append(str(row["role"]))
	return found


def _doctype_meta(client, doctype: str) -> tuple[dict | None, str]:
	try:
		result = client.call_method("frappe.desk.form.load.getdoctype", {"doctype": doctype})
	except ERPNextClientError as exc:
		kind = failure_kind(exc)
		if kind == "missing":
			return None, f"{doctype} is not installed on that site. Install the WhatsApp app there."
		if kind == "denied":
			return None, f"The API user is not allowed to open {doctype}."
		if kind == "down":
			return None, _sign_in_detail(exc)
		return None, f"Could not read {doctype} on that site. {exc}"
	meta = _meta_doc(result, doctype)
	if not meta:
		return None, f"{doctype} is not installed on that site. Install the WhatsApp app there."
	return meta, ""


def _meta_doc(result, doctype: str) -> dict | None:
	docs = []
	if isinstance(result, dict):
		docs = result.get("docs") or []
		if not docs and isinstance(result.get("message"), dict):
			docs = result["message"].get("docs") or []
	if not isinstance(docs, list):
		return None
	for doc in docs:
		if isinstance(doc, dict) and doc.get("name") == doctype:
			return doc
	first = docs[0] if docs else None
	return first if isinstance(first, dict) else None


def _message_list(result) -> list[str]:
	message = result.get("message") if isinstance(result, dict) else result
	if not isinstance(message, list):
		return []
	return [str(role) for role in message if role]


def failure_kind(exc: ERPNextClientError) -> str:
	text = str(exc).lower()
	if exc.status_code in (401, 403) or "refused the api" in text:
		return "denied"
	if exc.retryable or exc.status_code in (408, 429, 500, 502, 503, 504):
		return "down"
	if exc.status_code == 404 or "doesnotexist" in text or "not found" in text:
		return "missing"
	if "permission" in text:
		return "denied"
	return "other"


def _sign_in_detail(exc: ERPNextClientError, client: Any = None) -> str:
	kind = failure_kind(exc)
	if kind == "denied":
		if client and (getattr(client, "oauth_session", None) or getattr(client, "access_token", None)):
			return "The OAuth access token was refused or expired. Click Re-authorize to refresh access."
		return "The API key or API secret was refused. Generate a new key on that site and paste both values again."
	if kind == "down":
		text = str(exc).lower()
		if "did not respond" in text:
			return "The site did not respond in time. Check that the site is running, then save again."
		return "The site is not reachable, or its API is not responding. Check the site URL, then save again."
	return str(exc) or "Nudg could not sign in to that site."


def _result(*, ok: bool, status: str, remote_user: str, checks: list[dict]) -> dict:
	failed = [check["detail"] for check in checks if not check.get("ok")]
	if ok:
		reason = ""
	else:
		reason = " ".join(failed)[:1000]
	return {
		"ok": ok,
		"status": status,
		"remote_user": remote_user,
		"reason": reason,
		"checks": checks,
	}
