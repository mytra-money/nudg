// Nudg invitations pick one role, the way Frappe CRM does.
// The framework Roles table stays in the document so the invitation can be accepted.
frappe.ui.form.on("User Invitation", {
	refresh(frm) {
		show_nudg_role(frm);
	},
	app_name(frm) {
		show_nudg_role(frm);
	},
	nudg_role(frm) {
		if (frm.doc.app_name !== "nudg") return;
		copy_role(frm);
	},
});

function show_nudg_role(frm) {
	const nudg = frm.doc.app_name === "nudg";
	frm.toggle_display("nudg_role", nudg);
	frm.toggle_display("nudg_account", nudg);
	frm.toggle_display("roles", !nudg);
	if (!nudg) return;
	if (frm.is_new() && !frm.doc.redirect_to_path) {
		frm.set_value("redirect_to_path", "/nudg");
	}
	if (frm.is_new() && !frm.doc.nudg_role) {
		frm.set_value("nudg_role", "WhatsApp Manager");
		return;
	}
	copy_role(frm);
}

function copy_role(frm) {
	if (!frm.doc.nudg_role) return;
	const current = (frm.doc.roles || []).map((row) => row.role);
	if (current.length === 1 && current[0] === frm.doc.nudg_role) return;
	frm.clear_table("roles");
	frm.add_child("roles", { role: frm.doc.nudg_role });
	frm.refresh_field("roles");
}
