frappe.ui.form.on("WA Chatbot", {
	populate_hours_btn(frm) {
		frappe.call({
			method: "populate_default_business_hours",
			doc: frm.doc,
			callback(r) {
				if (r.message) {
					frappe.show_alert({ message: r.message.message || __("Business hours updated"), indicator: "green" });
					frm.reload_doc();
				}
			},
		});
	},
});
