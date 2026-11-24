frappe.ui.form.on("WA Campaign", {
	refresh(frm) {
		frm.set_df_property("recipients", "cannot_add_rows", true);
		frm.set_df_property("recipients", "cannot_delete_rows", true);
		const grid = frm.fields_dict.recipients && frm.fields_dict.recipients.grid;
		if (!grid) return;
		["mobile_number", "recipient_name", "recipient_data"].forEach((field) => {
			grid.update_docfield_property(field, "read_only", 1);
		});
		grid.update_docfield_property("unsubscribed", "read_only", 0);
	},
	recipient_type(frm) {
		frm.set_value("recipient", "");
		frm.clear_table("recipients");
		frm.refresh_field("recipients");
	},
	recipient(frm) {
		load_recipient_rows(frm);
	},
});

function load_recipient_rows(frm) {
	if (!frm.doc.recipient_type || !frm.doc.recipient) {
		frm.clear_table("recipients");
		frm.refresh_field("recipients");
		return;
	}
	frappe.call({
		method: "nudg.nudg.doctype.wa_campaign.wa_campaign.preview_recipients",
		args: {
			recipient_type: frm.doc.recipient_type,
			recipient: frm.doc.recipient,
		},
		callback(r) {
			frm.clear_table("recipients");
			(r.message || []).forEach((row) => frm.add_child("recipients", row));
			frm.refresh_field("recipients");
		},
	});
}
