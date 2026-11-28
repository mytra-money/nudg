app_name = "nudg"
app_title = "Nudg"
app_publisher = "Nudg"
app_description = "Nudg – Every conversation moves business forward."
app_email = "admin@example.com"
app_license = "MIT"
app_icon_url = "/assets/nudg/desk.svg"
app_icon_title = "Nudg"
app_icon_route = "/nudg"

app_include_js = ["/assets/nudg/js/nudg_navbar.js"]
app_include_css = ["/assets/nudg/css/nudg_navbar.css"]

doctype_js = {
	"WA Account": "public/js/wa_account.js",
	"WA Message": "public/js/wa_message.js",
	"WA Bulk Message": "public/js/wa_bulk_message.js",
	"WA Campaign": "public/js/wa_campaign.js",
	"WA Recipient List": "public/js/wa_recipient_list.js",
	"WA Chatbot": "public/js/wa_chatbot.js",
	"User Invitation": "public/js/user_invitation.js",
}

# Frappe v16+ target with official frappe/whatsapp integration
required_apps = ["whatsapp"]

add_to_apps_screen = [
	{
		"name": "nudg",
		"logo": "/assets/nudg/desk.svg",
		"title": "Nudg",
		"route": "/nudg",
		"has_permission": "nudg.api.has_app_permission",
	}
]

website_route_rules = [
	{"from_route": "/nudg/<path:app_path>", "to_route": "nudg"},
	{"from_route": "/nudg", "to_route": "nudg"},
]

after_install = "nudg.install.after_install"
after_migrate = ["nudg.install.after_migrate"]

# Standard Frappe invitation. WhatsApp Manager may invite either WhatsApp role.
# The invitee sets their own password from the email. No password is chosen here.
user_invitation = {
	"allowed_roles": {
		"System Manager": ["WhatsApp Manager", "WhatsApp User"],
		"WhatsApp Manager": ["WhatsApp Manager", "WhatsApp User"],
	},
	"extra_invite_params": ["nudg_account"],
	"after_accept": ["nudg.invitations.after_accept"],
}

permission_query_conditions = {
	"WA Profile": "nudg.security.get_tenant_conversation_query",
	"UTM Campaign": "nudg.security.get_tenant_campaign_query",
	"WA Quick Reply": "nudg.security.get_tenant_quick_reply_query",
	"WA Catalog": "nudg.security.get_tenant_catalog_query",
	"WA Catalog Item": "nudg.security.get_tenant_catalog_item_query",
	"WA Template": "nudg.security.get_tenant_template_query",
	"WA Bulk Message": "nudg.security.get_tenant_bulk_query",
	"WA Campaign": "nudg.security.get_tenant_whatsapp_campaign_query",
	"WA Recipient List": "nudg.security.get_tenant_recipient_list_query",
	"WA Chatbot": "nudg.security.get_tenant_chatbot_query",
	"WA Keyword Reply": "nudg.security.get_tenant_keyword_query",
	"WA AI Context": "nudg.security.get_tenant_ai_context_query",
	"WA Chatbot Session": "nudg.security.get_tenant_session_query",
	"WA Agent Transfer": "nudg.security.get_tenant_transfer_query",
}

has_permission = {
	"WA Profile": "nudg.security.has_tenant_permission",
	"UTM Campaign": "nudg.security.has_tenant_permission",
	"WA Quick Reply": "nudg.security.has_tenant_permission",
	"WA Catalog": "nudg.security.has_tenant_permission",
	"WA Catalog Item": "nudg.security.has_tenant_permission",
	"WA Template": "nudg.security.has_tenant_permission",
	"WA Bulk Message": "nudg.security.has_tenant_permission",
	"WA Campaign": "nudg.security.has_tenant_permission",
	"WA Recipient List": "nudg.security.has_tenant_permission",
	"WA Chatbot": "nudg.security.has_tenant_permission",
	"WA Keyword Reply": "nudg.security.has_tenant_permission",
	"WA AI Context": "nudg.security.has_tenant_permission",
	"WA Chatbot Session": "nudg.security.has_tenant_permission",
	"WA Agent Transfer": "nudg.security.has_tenant_permission",
}

export_python_type_annotations = True

# Meta may be pointed at the official webhook. This wrapper keeps the raw
# payload for chatbot button ids and WhatsApp Flow replies, then calls it.
override_whitelisted_methods = {
	"whatsapp.whatsapp.webhook.handler": "nudg.integrations.webhook.handler",
	"whatsapp.whatsapp.api.messages.send_message": "nudg.integrations.site_store.send_message",
	"whatsapp.whatsapp.api.messages.send_template": "nudg.integrations.site_store.send_template_message",
}

extend_bootinfo = ["nudg.desk_access.extend_bootinfo"]

doc_events = {
	"User": {
		"after_insert": [
			"nudg.security.on_user_created",
			"nudg.desk_access.assign_module_profile",
		],
	},
	"WA Account": {
		"validate": [
			"nudg.integrations.embedded_signup.lock_embedded_signup_account",
			"nudg.integrations.erpnext.service.validate_account_site",
		],
		"before_rename": "nudg.integrations.embedded_signup.block_embedded_signup_rename",
		"after_insert": [
			"nudg.security.undo_autoselected_default",
			"nudg.security.mark_first_account_default",
		],
		"on_update": "nudg.security.on_wa_account_change",
		"on_trash": "nudg.security.on_wa_account_change",
	},
	"WA Template": {
		"on_update": "nudg.security.on_template_change",
		"on_trash": "nudg.security.on_template_change",
	},
	"User Permission": {
		"on_update": "nudg.security.on_user_permission_change",
		"on_trash": "nudg.security.on_user_permission_change",
	},
	"User Invitation": {
		"before_insert": "nudg.invitations.prepare_nudg_invitation",
	},
	"WA Profile": {
		"on_update": "nudg.services.assignments.on_conversation_update",
	},
	"WA Message": {
		"before_insert": "nudg.services.automation.guard_duplicate_inbound",
		"before_validate": "nudg.services.outbound.bind_outgoing_account",
		"after_insert": [
			"nudg.services.automation.on_wa_message",
			"nudg.chatbot.processor.process_incoming_message",
			"nudg.integrations.site_sync.flag_message_for_client",
		],
		"on_submit": "nudg.integrations.site_sync.flag_message_for_client",
		"on_update": [
			"nudg.services.automation.on_wa_message",
			"nudg.services.bulk.sync_message_status",
		],
	},
}

scheduler_events = {
	"cron": {
		"* * * * *": [
			"nudg.services.campaigns.check_and_run_scheduled_campaigns",
			"nudg.services.bulk.process_scheduled_bulk_messages",
		],
		"*/5 * * * *": [
			"nudg.services.delivery.enqueue_fail_stuck_outgoing",
			"nudg.integrations.site_sync.sync_client_sites",
		],
	},
	"hourly": [
		"nudg.chatbot.session_manager.cleanup_expired_sessions",
	],
}
