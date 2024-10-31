# Copyright (c) 2024, DAS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder.functions import CombineDatetime, Sum
from frappe.utils import flt, now_datetime, nowtime, today


class BatchManufacture(Document):
	def autoname(self):
		td = now_datetime()
		self.bulan = td.month
		self.tahun = td.year
		
def on_doctype_update():
	frappe.db.add_unique("Batch Manufacture Sub Assembly", ["item_code", "parent"], constraint_name="unique_item_parent")

def get_auto_batch_manufacture(kwargs):
	available_batches = get_available_batches(kwargs)
	qty = flt(kwargs.qty)

	if not kwargs.consider_negative_batches:
		available_batches = list(filter(lambda x: x.qty > 0, available_batches))

	if not qty:
		return available_batches
	
	return get_qty_based_available_batches(available_batches, qty)

def get_qty_based_available_batches(available_batches, qty):
	batches = []
	for batch in available_batches:
		if qty <= 0:
			break

		batch_qty = flt(batch.qty)
		if qty > batch_qty:
			batches.append(
				frappe._dict(
					{
						"batch_manufacture": batch.batch_no,
						"qty": batch_qty,
						"warehouse": batch.warehouse,
					}
				)
			)
			qty -= batch_qty
		else:
			batches.append(
				frappe._dict(
					{
						"batch_manufacture": batch.batch_no,
						"qty": qty,
						"warehouse": batch.warehouse,
					}
				)
			)
			qty = 0

	return batches

def get_available_batches(kwargs):
	stock_ledger_entry = frappe.qb.DocType("Stock Ledger Entry")
	batch_table = frappe.qb.DocType("Batch Manufacture")

	query = (
		frappe.qb.from_(stock_ledger_entry)
		.inner_join(batch_table)
		.on(stock_ledger_entry.custom_batch == batch_table.name)
		.select(
			stock_ledger_entry.custom_batch.as_("batch_manufacture"),
			stock_ledger_entry.warehouse,
			Sum(stock_ledger_entry.actual_qty).as_("qty"),
		)
		.where(batch_table.disabled == 0)
		.where(stock_ledger_entry.is_cancelled == 0)
		.groupby(stock_ledger_entry.item_code, stock_ledger_entry.custom_batch, stock_ledger_entry.warehouse)
	)

	if not kwargs.get("for_stock_levels"):
		query = query.where((batch_table.expiry_date >= today()) | (batch_table.expiry_date.isnull()))

	if kwargs.get("posting_date"):
		if kwargs.get("posting_time") is None:
			kwargs.posting_time = nowtime()

		timestamp_condition = CombineDatetime(
			stock_ledger_entry.posting_date, stock_ledger_entry.posting_time
		) <= CombineDatetime(kwargs.posting_date, kwargs.posting_time)

		query = query.where(timestamp_condition)

	for field in ["warehouse", "item_code"]:
		if not kwargs.get(field):
			continue

		if isinstance(kwargs.get(field), list):
			query = query.where(stock_ledger_entry[field].isin(kwargs.get(field)))
		else:
			query = query.where(stock_ledger_entry[field] == kwargs.get(field))

	if kwargs.get("batch_no"):
		if isinstance(kwargs.batch_no, list):
			query = query.where(batch_table.name.isin(kwargs.batch_no))
		else:
			query = query.where(batch_table.name == kwargs.batch_no)

	if kwargs.based_on == "LIFO":
		query = query.orderby(batch_table.creation, order=frappe.qb.desc)
	elif kwargs.based_on == "Expiry":
		query = query.orderby(batch_table.expiry_date)
	else:
		query = query.orderby(batch_table.creation)

	if kwargs.get("ignore_voucher_nos"):
		query = query.where(stock_ledger_entry.voucher_no.notin(kwargs.get("ignore_voucher_nos")))
		
	data = query.run(as_dict=True)

	return data