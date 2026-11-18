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

permission_query_conditions = {
	"WA Profile": "nudg.security.get_tenant_conversation_query",
	"UTM Campaign": "nudg.security.get_tenant_campaign_query",
	"WA Automation Rule": "nudg.security.get_tenant_rule_query",
	"WA Quick Reply": "nudg.security.get_tenant_quick_reply_query",
	"WA Catalog": "nudg.security.get_tenant_catalog_query",
}

has_permission = {
	"WA Profile": "nudg.security.has_tenant_permission",
	"UTM Campaign": "nudg.security.has_tenant_permission",
	"WA Automation Rule": "nudg.security.has_tenant_permission",
	"WA Quick Reply": "nudg.security.has_tenant_permission",
	"WA Catalog": "nudg.security.has_tenant_permission",
}

export_python_type_annotations = True

extend_bootinfo = ["nudg.desk_access.extend_bootinfo"]

doc_events = {
	"User": {
		"after_insert": [
			"nudg.security.on_user_created",
			"nudg.desk_access.assign_module_profile",
		],
	},
	"WA Account": {
		"validate": "nudg.integrations.erpnext.service.validate_account_site",
		"after_insert": "nudg.security.undo_autoselected_default",
	},
	"WA Profile": {
		"on_update": "nudg.services.assignments.on_conversation_update",
	},
	"WA Message": {
		"after_insert": "nudg.services.automation.on_wa_message",
		"on_update": "nudg.services.automation.on_wa_message",
	},
}

scheduler_events = {
	"cron": {
		"* * * * *": [
			"nudg.services.campaigns.check_and_run_scheduled_campaigns",
			"nudg.services.delivery.fail_stuck_outgoing",
		]
	},
}
