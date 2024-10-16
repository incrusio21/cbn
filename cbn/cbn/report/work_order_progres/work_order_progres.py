# Copyright (c) 2024, DAS and contributors
# For license information, please see license.txt

import frappe
from frappe import _

def execute(filters=None):
	data = get_result(filters)

	columns = get_columns(filters)

	return columns, data

def get_result(filters):
	ress = []

	progress = frappe.db.sql(""" 
		SELECT 
			custom_batch as batch, wo.production_item as item_code, wo.item_name, wo.qty, wo.name as work_order, wo.status as status, 
			jc.operation, jc.workstation, jc.wip_warehouse as warehouse, jc.status as job_card_status, wo.company
		FROM `tabWork Order` wo
		LEFT JOIN `tabJob Card` jc on wo.name = jc.work_order and jc.docstatus < 2
		WHERE custom_batch = %(batch)s and wo.docstatus = 1
	""", filters, as_dict=1)

	work_order = {}
	for row in progress:
		wo_list = work_order.setdefault(row.work_order, [])
		wo_progress = {
			"operation": row.operation, "workstation": row.workstation, "warehouse": row.warehouse, "job_card_status": row.job_card_status,
			"company": row.company
		}

		if not wo_list:
			wo_progress.update(row)

		wo_list.append(wo_progress)

	for data in work_order.values():
		ress.extend(data)

	return ress

def get_columns(filters):
	columns = [
		{
			"label": _("Batch"),
			"fieldname": "batch",
			"fieldtype": "Link",
			"options": "Batch",
			"width": 180,
		},
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 180,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
		},
		{
			"label": _("Qty"),
			"fieldname": "qty",
			"fieldtype": "Float",
		},
		{
			"label": _("Work Order"),
			"fieldname": "work_order",
			"fieldtype": "Link",
			"options": "Work Order",
		},
		{
			"label": _("Status"),
			"fieldname": "status",
			"fieldtype": "Data",
		},
		{
			"label": _("Operation"),
			"fieldname": "operation",
			"fieldtype": "Link",
			"options": "Operation",
		},
		{
			"label": _("Workstation"),
			"fieldname": "workstation",
			"fieldtype": "Link",
			"options": "Workstation",
		},
		{
			"label": _("Status"),
			"fieldname": "job_card_status",
			"fieldtype": "Data"
		},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
		},
	]

	return columns
