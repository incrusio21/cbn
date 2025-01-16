# Copyright (c) 2024, DAS and contributors
# For license information, please see license.txt

import frappe
from frappe import _, _dict
from frappe.query_builder.functions import CombineDatetime, IfNull, Sum

from erpnext.stock.doctype.warehouse.warehouse import apply_warehouse_filter
from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
from erpnext.stock.utils import (
	is_reposting_item_valuation_in_progress,
)
from frappe.utils.data import cint, flt

def execute(filters=None):
	is_reposting_item_valuation_in_progress()
	data = []
	include_uom = filters.get("include_uom")

	columns = get_columns(filters)
	items = get_items(filters)
	sl_entries = get_stock_ledger_entries(filters, items)
	item_details = get_item_details(items, sl_entries, include_uom)

	opening_row = get_opening_balance_from_batch(filters, columns, sl_entries)
	precision = cint(frappe.db.get_single_value("System Settings", "float_precision"))
	
	item_list = {}
	for row in opening_row:
		key = tuple([row.item_code, row.warehouse])
		item_list.setdefault(key, _dict({
			"qty_after_transaction": row.qty_after_transaction,
			"stock_value": row.stock_value
		}))

	for sle in sl_entries:
		item_detail = item_details[sle.item_code]

		sle.update(item_detail)
		
		key = tuple([sle.item_code, sle.warehouse])
		item = item_list.get(key)
		if not item:
			item = item_list.setdefault(key, _dict({
				"qty_after_transaction": 0,
				"stock_value": 0
			}))

		item.qty_after_transaction += flt(sle.actual_qty, precision)
		item.stock_value += sle.stock_value_difference

		sle.update({"qty_after_transaction": item.qty_after_transaction, "stock_value": item.stock_value})
		sle.update({"in_qty": max(sle.actual_qty, 0), "out_qty": min(sle.actual_qty, 0)})

		if sle.actual_qty:
			sle["in_out_rate"] = flt(sle.stock_value_difference / sle.actual_qty, precision)

		elif sle.voucher_type == "Stock Reconciliation":
			sle["in_out_rate"] = sle.valuation_rate
			
		data.append(sle)

	return columns, data

def get_columns(filters):
	columns = [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Datetime", "width": 150},
		{
			"label": _("Batch"), 
			"fieldname": "custom_batch", 
			"fieldtype": "Link", 
			"options": "Batch Manufacture",
			"width": 150
		},
		{
			"label": _("Item"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 100,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "width": 100},
		{
			"label": _("Stock UOM"),
			"fieldname": "stock_uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 90,
		},
		{
			"label": _("In Qty"),
			"fieldname": "in_qty",
			"fieldtype": "Float",
			"width": 80,
			"convertible": "qty",
		},
		{
			"label": _("Out Qty"),
			"fieldname": "out_qty",
			"fieldtype": "Float",
			"width": 80,
			"convertible": "qty",
		},
		{
			"label": _("Balance Qty"),
			"fieldname": "qty_after_transaction",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 150,
		},
		{
			"label": _("Incoming Rate"),
			"fieldname": "incoming_rate",
			"fieldtype": "Currency",
			"width": 110,
			"options": "Company:company:default_currency",
			"convertible": "rate",
		},
		{
			"label": _("Avg Rate (Balance Stock)"),
			"fieldname": "valuation_rate",
			"fieldtype": "Currency",
			"width": 180,
			"options": "Company:company:default_currency",
			"convertible": "rate",
		},
		{
			"label": _("Valuation Rate"),
			"fieldname": "in_out_rate",
			"fieldtype": "Currency",
			"width": 140,
			"options": "Company:company:default_currency",
			"convertible": "rate",
		},
		{
			"label": _("Balance Value"),
			"fieldname": "stock_value",
			"fieldtype": "Currency",
			"width": 110,
			"options": "Company:company:default_currency",
		},
		{
			"label": _("Value Change"),
			"fieldname": "stock_value_difference",
			"fieldtype": "Currency",
			"width": 110,
			"options": "Company:company:default_currency",
		},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "width": 110},
		{
			"label": _("Voucher #"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 100,
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 110,
		},
	]

	return columns

def get_inventory_dimension_fields():
	return [dimension.fieldname for dimension in get_inventory_dimensions()]

def get_stock_ledger_entries(filters, items):
	sle = frappe.qb.DocType("Stock Ledger Entry")
	query = (
		frappe.qb.from_(sle)
		.select(
			sle.item_code,
			sle.posting_datetime.as_("date"),
			sle.warehouse,
			sle.posting_date,
			sle.posting_time,
			sle.actual_qty,
			sle.incoming_rate,
			sle.valuation_rate,
			sle.company,
			sle.voucher_type,
			sle.stock_value_difference,
			sle.voucher_no,
			sle.stock_value,
			sle.custom_batch,
			sle.project,
		)
		.where(
			(sle.docstatus < 2)
			& (sle.is_cancelled == 0)
			& (sle.posting_date[filters.from_date : filters.to_date])
		)
		.orderby(CombineDatetime(sle.posting_date, sle.posting_time))
		.orderby(sle.creation)
	)

	inventory_dimension_fields = get_inventory_dimension_fields()
	if inventory_dimension_fields:
		for fieldname in inventory_dimension_fields:
			query = query.select(fieldname)
			if fieldname in filters and filters.get(fieldname):
				query = query.where(sle[fieldname].isin(filters.get(fieldname)))

	if items:
		query = query.where(sle.item_code.isin(items))

	for field in ["voucher_no", "project", "company"]:
		if filters.get(field) and field not in inventory_dimension_fields:
			query = query.where(sle[field] == filters.get(field))

	if filters.get("batch"):
		query = query.where(sle.custom_batch == filters.batch)
	else:
		query = query.where(IfNull(sle.custom_batch, "") != "")

	query = apply_warehouse_filter(query, sle, filters)

	return query.run(as_dict=True, debug=1)

def get_opening_balance_from_batch(filters, columns, sl_entries):
	query_filters = {
		"custom_batch": filters.batch or ["is", "not set"],
		"docstatus": 1,
		"is_cancelled": 0,
		"posting_date": ("<", filters.from_date),
		"company": filters.company,
	}

	for fields in ["item_code", "warehouse"]:
		if filters.get(fields):
			query_filters[fields] = filters.get(fields)

	return frappe.get_all(
		"Stock Ledger Entry",
		fields=["item_code", "warehouse","sum(actual_qty) as qty_after_transaction", "sum(stock_value_difference) as stock_value"],
		filters=query_filters,
		group_by="item_code, warehouse",
		debug=1
	)

def get_item_details(items, sl_entries, include_uom):
	item_details = {}
	if not items:
		items = list(set(d.item_code for d in sl_entries))

	if not items:
		return item_details

	item = frappe.qb.DocType("Item")
	query = (
		frappe.qb.from_(item)
		.select(item.name, item.item_name, item.description, item.item_group, item.brand, item.stock_uom)
		.where(item.name.isin(items))
	)

	if include_uom:
		ucd = frappe.qb.DocType("UOM Conversion Detail")
		query = (
			query.left_join(ucd)
			.on((ucd.parent == item.name) & (ucd.uom == include_uom))
			.select(ucd.conversion_factor)
		)

	res = query.run(as_dict=True)

	for item in res:
		item_details.setdefault(item.name, item)

	return item_details

def get_items(filters):
	item = frappe.qb.DocType("Item")
	query = frappe.qb.from_(item).select(item.name)
	conditions = []

	if item_code := filters.get("item_code"):
		conditions.append(item.name == item_code)
	else:
		if brand := filters.get("brand"):
			conditions.append(item.brand == brand)
		if item_group := filters.get("item_group"):
			if condition := get_item_group_condition(item_group, item):
				conditions.append(condition)

	items = []
	if conditions:
		for condition in conditions:
			query = query.where(condition)
		items = [r[0] for r in query.run()]

	return items

def get_item_group_condition(item_group, item_table=None):
	item_group_details = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=1)
	if item_group_details:
		if item_table:
			ig = frappe.qb.DocType("Item Group")
			return item_table.item_group.isin(
				frappe.qb.from_(ig)
				.select(ig.name)
				.where(
					(ig.lft >= item_group_details.lft)
					& (ig.rgt <= item_group_details.rgt)
					& (item_table.item_group == ig.name)
				)
			)
		else:
			return f"item.item_group in (select ig.name from `tabItem Group` ig \
				where ig.lft >= {item_group_details.lft} and ig.rgt <= {item_group_details.rgt} and item.item_group = ig.name)"