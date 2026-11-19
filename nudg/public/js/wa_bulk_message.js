frappe.ui.form.on("WA Bulk Message", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Scheduled") {
			frm.dashboard.set_headline(
				__("This message is scheduled for {0}", [frappe.datetime.str_to_user(frm.doc.scheduled_time)]),
				"blue"
			);
		}
		if (frm.doc.docstatus !== 1 || frm.doc.status === "Draft") {
			return;
		}
		frm.add_custom_button(__("Check Progress"), () => {
			frappe.call({
				method: "nudg.services.bulk.get_bulk_progress",
				args: { name: frm.doc.name },
				callback(r) {
					const progress = r.message || {};
					const percent = Math.round(progress.percent || 0);
					frappe.msgprint({
						title: __("Message Progress"),
						indicator: "blue",
						message: `
							<div class="progress" style="height: 20px;">
								<div class="progress-bar bg-success" style="width: ${percent}%;">${percent}%</div>
							</div>
							<div class="mt-2">
								<span class="badge badge-success">Sent: ${progress.sent || 0}</span>
								<span class="badge badge-danger ml-2">Failed: ${progress.failed || 0}</span>
								<span class="badge badge-warning ml-2">Queued: ${progress.queued || 0}</span>
								<span class="badge badge-info ml-2">Total: ${progress.total || 0}</span>
							</div>
						`,
					});
				},
			});
		});
		frm.add_custom_button(__("Retry Failed"), () => {
			frappe.call({
				method: "nudg.services.bulk.retry_failed_messages",
				args: { name: frm.doc.name },
				callback() {
					frm.reload_doc();
				},
			});
		});
	},
});
