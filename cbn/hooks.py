app_name = "cbn"
app_title = "Cbn"
app_publisher = "DAS"
app_description = "CBN"
app_email = "das@gmail.com"
app_license = "mit"
# required_apps = []

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/cbn/css/cbn.css"
# app_include_js = "/assets/cbn/js/cbn.js"

# include js, css files in header of web template
# web_include_css = "/assets/cbn/css/cbn.css"
# web_include_js = "/assets/cbn/js/cbn.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "cbn/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "BOM" : "cbn/custom/bom.js",
    "Item" : "cbn/custom/item.js",
    "Delivery Note" : "cbn/custom/delivery_note.js",
    "Job Card" : "cbn/custom/job_card.js",
    "Sales Order" : "cbn/custom/sales_order.js",
    "Stock Entry" : "cbn/custom/stock_entry.js",
	"Production Plan": "cbn/custom/production_plan.js",
    "Quality Inspection" : "cbn/custom/quality_inspection.js",
    "Work Order" : "cbn/custom/work_order.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "cbn/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "cbn.utils.jinja_methods",
# 	"filters": "cbn.utils.jinja_filters"
# }

fixtures = [
    {
        "dt": "Stock Entry Type", 
        "filters": [
        	[
				"name", "in", [
                    "Return of Remaining Goods", "Manufacture Conversion"
				]
			]
    	]
    }
]
# Installation
# ------------

# before_install = "cbn.install.before_install"
# after_install = "cbn.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "cbn.uninstall.before_uninstall"
# after_uninstall = "cbn.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "cbn.utils.before_app_install"
# after_app_install = "cbn.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "cbn.utils.before_app_uninstall"
# after_app_uninstall = "cbn.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "cbn.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"BOM": "cbn.overrides.bom.BOM",
	"Item": "cbn.overrides.item.Item",
	# "Quality Inspection": "cbn.overrides.quality_inspection.QualityInspection",
	"Production Plan": "cbn.overrides.production_plan.ProductionPlan",
	"Stock Entry": "cbn.overrides.stock_entry.StockEntry",
	"Stock Ledger Entry": "cbn.overrides.stock_ledger_entry.StockLedgerEntry",
	"Stock Reconciliation": "cbn.overrides.stock_reconciliation.StockReconciliation",
	"Work Order": "cbn.overrides.work_order.WorkOrder",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	# "*": {
	# 	"on_update": "method",
	# 	"on_cancel": "method",
	# 	"on_trash": "method"
	# }
    "Item": {
		"validate": "cbn.cbn.custom.item.validate_item_parent"
	},
    "BOM": {
        "validate": "cbn.cbn.custom.bom.calculate_total_qty"
    },
    "Stock Entry": {
        "on_submit": "cbn.cbn.custom.stock_entry.validate_and_update_loss_item",
        "on_cancel": "cbn.cbn.custom.stock_entry.validate_and_update_loss_item",
        "validate": "cbn.cbn.custom.stock_entry.calculate_total_qty"
    },
    "Production Plan": {
        "on_submit": ["cbn.cbn.custom.production_plan.update_batch_manufacture", "cbn.cbn.custom.production_plan.add_conversion_batch_manufacture"],
        "on_cancel": ["cbn.cbn.custom.production_plan.update_batch_manufacture"],
	},
    "Quality Inspection": {
        "validate": "cbn.cbn.custom.quality_inspection.set_job_card_bm"
	},
    "Work Order": {
        "validate": "cbn.cbn.custom.work_order.WorkOrder",
        "before_update_after_submit": "cbn.cbn.custom.work_order.WorkOrder",
        "on_submit": "cbn.cbn.custom.work_order.WorkOrder",
        "on_cancel": "cbn.cbn.custom.work_order.WorkOrder",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"cbn.tasks.all"
# 	],
# 	"daily": [
# 		"cbn.tasks.daily"
# 	],
# 	"hourly": [
# 		"cbn.tasks.hourly"
# 	],
# 	"weekly": [
# 		"cbn.tasks.weekly"
# 	],
# 	"monthly": [
# 		"cbn.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "cbn.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	"erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry": "cbn.cbn.custom.work_order.make_stock_entry",
    "erpnext.controllers.stock_controller.make_quality_inspections": "cbn.controllers.stock_controller.make_quality_inspections"
}

#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "cbn.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["cbn.utils.before_request"]
# after_request = ["cbn.utils.after_request"]

# Job Events
# ----------
# before_job = ["cbn.utils.before_job"]
# after_job = ["cbn.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"cbn.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

