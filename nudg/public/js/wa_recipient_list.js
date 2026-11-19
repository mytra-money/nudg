frappe.ui.form.on("WA Recipient List", {
	refresh(frm) {
		if (frm.fields_dict.import_button) {
			frm.fields_dict.import_button.onclick = () => import_recipients(frm);
		}
		if (frm.is_new()) {
			return;
		}
		frm.add_custom_button(__("Add Recipient"), () => {
			const dialog = new frappe.ui.Dialog({
				title: __("Add Recipient"),
				fields: [
					{ label: __("Mobile Number"), fieldname: "mobile_number", fieldtype: "Data", reqd: 1 },
					{ label: __("Recipient Name"), fieldname: "recipient_name", fieldtype: "Data" },
					{ label: __("Recipient Data"), fieldname: "recipient_data", fieldtype: "Code", options: "JSON" },
				],
				primary_action_label: __("Add"),
				primary_action(values) {
					if (values.recipient_data) {
						JSON.parse(values.recipient_data);
					}
					frm.add_child("recipients", values);
					frm.refresh_field("recipients");
					frm.dirty();
					dialog.hide();
				},
			});
			dialog.show();
		});
		frm.add_custom_button(__("Validate Numbers"), () => {
			const invalid = [];
			(frm.doc.recipients || []).forEach((row, index) => {
				const mobile = (row.mobile_number || "").replace(/[^\d+]/g, "");
				if (mobile.replace(/\+/g, "").length < 10) {
					invalid.push({ idx: index + 1, mobile: row.mobile_number });
				}
			});
			if (!invalid.length) {
				frappe.msgprint({ title: __("Validation"), message: __("All numbers look valid."), indicator: "green" });
				return;
			}
			const lines = invalid.map((row) => `<li>${row.idx}: ${frappe.utils.escape_html(row.mobile || "")}</li>`).join("");
			frappe.msgprint({
				title: __("Invalid numbers"),
				indicator: "red",
				message: `<ul>${lines}</ul>`,
			});
		});
	},
});

function import_recipients(frm) {
	if (!frm.doc.doctype_to_import || !frm.doc.mobile_field) {
		frappe.throw(__("Select a DocType and a mobile field first."));
	}
	let filters = null;
	let data_fields = null;
	if (frm.doc.import_filters) {
		filters = JSON.parse(frm.doc.import_filters);
	}
	if (frm.doc.data_fields) {
		data_fields = JSON.parse(frm.doc.data_fields);
	}
	frappe.call({
		method: "nudg.services.bulk.import_recipients",
		args: {
			list_name: frm.doc.name,
			doctype: frm.doc.doctype_to_import,
			mobile_field: frm.doc.mobile_field,
			name_field: frm.doc.name_field,
			filters,
			limit: frm.doc.import_limit,
			data_fields,
		},
		callback(r) {
			frappe.show_alert({ message: __("{0} recipients imported", [r.message || 0]), indicator: "green" });
			frm.reload_doc();
		},
	});
}
