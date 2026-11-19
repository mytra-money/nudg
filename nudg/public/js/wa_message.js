// Copyright (c) 2026, Nudg and contributors
// For license information, please see license.txt

// The official form fills a new outgoing message from WA Settings.default_account.
// The recipient profile already names the number that owns the chat.
frappe.ui.form.on("WA Message", {
	refresh(frm) {
		apply_profile_account(frm);
	},
	to(frm) {
		frm._nudg_profile_account = null;
		apply_profile_account(frm);
	},
	whatsapp_account(frm) {
		const account = frm._nudg_profile_account;
		if (!account || frm.doc.docstatus || frm.doc.direction !== "Outgoing") return;
		if (frm.doc.whatsapp_account && frm.doc.whatsapp_account !== account) {
			frm.set_value("whatsapp_account", account);
		}
	},
});

function apply_profile_account(frm) {
	if (frm.doc.docstatus || frm.doc.direction !== "Outgoing" || !frm.doc.to) return;
	frappe.db.get_value("WA Profile", frm.doc.to, "whatsapp_account", (r) => {
		const account = r && r.whatsapp_account;
		if (!account) return;
		frm._nudg_profile_account = account;
		if (frm.doc.whatsapp_account !== account) {
			frm.set_value("whatsapp_account", account);
		}
	});
}
