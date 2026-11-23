// Copyright (c) 2026, Nudg and contributors
// For license information, please see license.txt

// Embedded Signup stores the Meta account. Those fields stay read-only.
const NUDG_EMBEDDED_ACCOUNT_FIELDS = [
	"account_name",
	"business_id",
	"phone_id",
	"app_id",
	"access_token",
];

frappe.ui.form.on("WA Account", {
	refresh(frm) {
		const locked = Number(frm.doc.embedded_signup) === 1;
		NUDG_EMBEDDED_ACCOUNT_FIELDS.forEach((fieldname) => {
			frm.set_df_property(fieldname, "read_only", locked ? 1 : 0);
		});
		frm.set_df_property("embedded_signup", "read_only", 1);
		frm.meta.allow_rename = locked ? 0 : 1;
	},
});
