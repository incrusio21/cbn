// Copyright (c) 2024, DAS and contributors
// For license information, please see license.txt

frappe.query_reports["Work Order Progres"] = {
	"filters": [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "batch",
			label: __("Batch"),
			fieldtype: "Link",
			options: "Batch Manufacture",
			// reqd: 1,
		},
	]
};
