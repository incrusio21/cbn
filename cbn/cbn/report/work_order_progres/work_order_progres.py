# Copyright (c) 2024, DAS and contributors
# For license information, please see license.txt

import frappe
from frappe import _, scrub

def execute(filters=None):
	data = [] # get_result(filters)
	work_order, additional_columns = get_work_order(filters)
	manufacture = get_manufacture(list(work_order.keys()))
	columns = get_columns(filters, additional_columns)

	for wo, value in work_order.items():
		data.append({
			"work_order": wo,
			**value,
			**manufacture.get(wo, {})
		})

	return columns, data

def get_work_order(filters):
	wo = frappe.qb.DocType("Work Order")
	jc = frappe.qb.DocType("Job Card")

	query = (
		frappe.qb.from_(wo)
		.inner_join(jc)
		.on((jc.work_order == wo.name) & (jc.docstatus == 1))
		.select(
			wo.name, wo.custom_batch, wo.batch_size, wo.production_item,
			jc.operation, jc.workstation, jc.total_completed_qty, jc.wip_warehouse, jc.actual_start_date, jc.actual_end_date
		)
		.where(wo.docstatus == 1)
	)

	if filters.get("batch"):
		query = query.where(wo.custom_batch == filters.batch)

	progress = query.run()
	
	work_order, operation = {}, set()
	wo_field = ["batch", "batch_size", "production_item"]
	jc_field = ["operation", "workstation", "completed_qty", "wip_warehouse", "start_date", "end_date"]
	for r in progress:
		wo_list = work_order.setdefault(r[0], frappe._dict(zip(wo_field, r[1:4])))
		
		dict_operation = frappe._dict(zip(jc_field, r[4:]))
		operation.add(dict_operation.operation)
		if dict_operation.operation == "Timbang":
			wo_list.update({ "tgl_timbang": dict_operation.start_date, "selesai_timbang": dict_operation.end_date })
		elif dict_operation.operation == "Mixing":
			wo_list.update({ "tgl_mixing": dict_operation.start_date })
		elif dict_operation.operation == "Filling":
			wo_list.update({ "tgl_filling": dict_operation.start_date, "aktual_filling": dict_operation.completed_qty })
		elif dict_operation.operation == "Coding":
			wo_list.update({ "tgl_coding": dict_operation.start_date, "qty_coding": dict_operation.completed_qty })
		elif dict_operation.operation == "Packing":
			wo_list.update({ "tgl_packing": dict_operation.start_date, "aktual_packing": dict_operation.completed_qty })

	additional_columns = operation_column(operation)
	
	return work_order, additional_columns

def get_manufacture(wo_list):
	ste = frappe.qb.DocType("Stock Entry")

	query = (
		frappe.qb.from_(ste)
		.select(
			ste.work_order, ste.posting_date
		)
		.where(
			(ste.stock_entry_type == "Manufacture") & (ste.docstatus == 1)
			& ste.work_order.isin(wo_list)
		)
	)

	manufacture = query.run()
	ste_field = ["tgl_kirim"]
	brg_jadi = {}
	for r in manufacture:
		wo_list = brg_jadi.setdefault(r[0], frappe._dict(zip(ste_field, r[1:])))

	return brg_jadi

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

def operation_column(operation):
	additional_columns = []
	
	if "Timbang" in operation:
		additional_columns.extend([
			{
				"label": _("Tgl Timbang"),
				"fieldname": "tgl_timbang",
				"fieldtype": "Date",
			},
			{
				"label": _("Selesai Timbang"),
				"fieldname": "selesai_timbang",
				"fieldtype": "Date",
			},
			{
				"label": _("Ket. Bahan Baku"),
				"fieldname": "bahan_baku",
				"fieldtype": "Data",
			},
			{
				"label": _("Verifikasi Bahan"),
				"fieldname": "varifikasi_bahan",
				"fieldtype": "Data",
			},
			
		])

	additional_columns.extend([
		{
			"label": _("Line Produksi"),
			"fieldname": "line_produksi",
			"fieldtype": "Int",
		},
	])

	if "Mixing" in operation:
		additional_columns.extend([
			{
				"label": _("Tgl Mixing"),
				"fieldname": "tgl_mixing",
				"fieldtype": "Date",
				"width": 120
			},
			{
				"label": _("Aktual (kg)"),
				"fieldname": "aktual_mixing",
				"fieldtype": "Float",
			},
			{
				"label": _("Rekonsiliasi Mixing"),
				"fieldname": "rekonsilasi_mixing",
				"fieldtype": "Percent",
			},
			{
				"label": _("Cek Rekon Mixing"),
				"fieldname": "cek_rekonsilasi_mixing",
				"fieldtype": "Data",
			},
			{
				"label": _("Penyimpangan Mixing"),
				"fieldname": "penyimpanngan_mixing",
				"fieldtype": "Data",
			},
			{
				"label": _("Pengujian Mixing (H0)"),
				"fieldname": "pengujian_mixing",
				"fieldtype": "Data",
			},
			{
				"label": _("Status Ruahan"),
				"fieldname": "status_ruahan",
				"fieldtype": "Data",
			},
			{
				"label": _("Uji Ruah 2"),
				"fieldname": "uji_ruah_2",
				"fieldtype": "Data",
			},
			{
				"label": _("Uji Ruah 3"),
				"fieldname": "uji_ruah_3",
				"fieldtype": "Data",
			},
			{
				"label": _("Uji Ruah 4"),
				"fieldname": "uji_ruah_4",
				"fieldtype": "Data",
			},
			{
				"label": _("Noted Produk Ruah"),
				"fieldname": "noted_produk_ruah",
				"fieldtype": "Data",
			},
			{
				"label": _("Tgl. Rework"),
				"fieldname": "tgl_rework",
				"fieldtype": "Date",
			},
			{
				"label": _("Turun PK1"),
				"fieldname": "turun_pk1",
				"fieldtype": "Date",
			},
			{
				"label": _("Krm Kemas P"),
				"fieldname": "krm_kemas_p",
				"fieldtype": "Date",
			},
			{
				"label": _("Ket. Kemas Primer"),
				"fieldname": "ket_kemas_primer",
				"fieldtype": "Data",
			},
			{
				"label": _("Turun PK2"),
				"fieldname": "turun_pk2",
				"fieldtype": "Date",
			},
			{
				"label": _("Krm Kemas S&T"),
				"fieldname": "krm_kemas_s_t",
				"fieldtype": "Date",
			},
			{
				"label": _("Ket. Kemas S&T"),
				"fieldname": "ket_kemas_s_t",
				"fieldtype": "Data",
			},
		])

	additional_columns.extend([
		{
			"label": _("Tgl Cleaning Botol"),
			"fieldname": "tgl_cleaning_botol",
			"fieldtype": "Date",
		},
		{
			"label": _("Qty Cleaning Botol (Pcs)"),
			"fieldname": "qty_cleaning_botol",
			"fieldtype": "Float",
		},
		{
			"label": _("Tgl Stiker Botol"),
			"fieldname": "tgl_stiker_botol",
			"fieldtype": "Date",
		},
		{
			"label": _("Qty Stiker Botol (Pcs)"),
			"fieldname": "qty_stiker_botol",
			"fieldtype": "Float",
		},
	])
	
	if "Filling" in operation:
		additional_columns.extend([
			{
				"label": _("Tgl Filling"),
				"fieldname": "tgl_filling",
				"fieldtype": "Date",
				"width": 120,
			},
			{
				"label": _("Aktual Filling (Pcs)"),
				"fieldname": "aktual_filling",
				"fieldtype": "Float",
			},
			{
				"label": _("Rekonsiliasi Filling"),
				"fieldname": "rekonsilasi_filling",
				"fieldtype": "Percent",
			},
			{
				"label": _("Cek Rekon Filling"),
				"fieldname": "cek_rekonsilasi_filling",
				"fieldtype": "Data",
			},
			{
				"label": _("Status Prd Filling"),
				"fieldname": "status_prd_filling",
				"fieldtype": "Data",
			},
		])

	if "Coding" in operation:
		additional_columns.extend([
			{
				"label": _("Tgl Coding"),
				"fieldname": "tgl_coding",
				"fieldtype": "Date",
				"width": 120,

			},
			{
				"label": _("Qty Coding (kg)"),
				"fieldname": "qty_coding",
				"fieldtype": "Float",
			},
		])

	if "Coding" in operation:
		additional_columns.extend([
			{
				"label": _("Tgl Packing"),
				"fieldname": "tgl_packing",
				"fieldtype": "Date",
				"width": 120,

			},
			{
				"label": _("Aktual Packing (kg)"),
				"fieldname": "aktual_packing",
				"fieldtype": "Float",
			},
			{
				"label": _("Rekonsiliasi Packing"),
				"fieldname": "rekonsiliasi_packing",
				"fieldtype": "Percent",
			},
			{
				"label": _("Cek Rekon Packing"),
				"fieldname": "cek_rekon_packing",
				"fieldtype": "Data",
			},
			{
				"label": _("Status Prd Packing"),
				"fieldname": "status_prd_packing",
				"fieldtype": "Data",
			},
		])

	return additional_columns

def get_columns(filters, operation_field):
	columns = [
		{
			"label": _("Work Order"),
			"fieldname": "work_order",
			"fieldtype": "Link",
			"options": "Work Order",
			"width": 200,
		},
		{
			"label": _("No. Batch"),
			"fieldname": "batch",
			"fieldtype": "Link",
			"options": "Batch",
			"width": 180,
		},
		{
			"label": _("Batch Size"),
			"fieldname": "batch",
			"fieldtype": "Float",
			"width": 80,
		},
		{
			"label": _("Merk"),
			"fieldname": "merk",
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": _("Varian"),
			"fieldname": "production_item",
			"fieldtype": "Link",
			"options": "Item",
			"width": 100,
		},
		{
			"label": _("Gramasi"),
			"fieldname": "gramasi",
			"fieldtype": "Data",
		},
		{
			"label": _("Pcs/Krt"),
			"fieldname": "pcs_krt",
			"fieldtype": "Data",
		},
		{
			"label": _("Turun PP"),
			"fieldname": "turun_pp",
			"fieldtype": "Data",
		},
		{
			"label": _("Turun CPB"),
			"fieldname": "turun_cpb",
			"fieldtype": "Data",
		},
	]

	columns.extend([
		*operation_field,
		{
			"label": _("Tgl Kirim"),
			"fieldname": "tgl_kirim",
			"fieldtype": "Date",
			"width": 120
		},
		{
			"label": _("KRT"),
			"fieldname": "krt",
			"fieldtype": "Int",
		},
		{
			"label": _("PCS"),
			"fieldname": "pcs_barang_jadi",
			"fieldtype": "Float",
		},
		{
			"label": _("Σ PCS"),
			"fieldname": "s_pcs_barang_jadi",
			"fieldtype": "Float",
		},
		{
			"label": _("Cek"),
			"fieldname": "cek_barang_jadi",
			"fieldtype": "Data",
		},
	])
	
	return columns

# column yg mungkin tidak akan d gunakan
# {
# 	"label": _("Item Code"),
# 	"fieldname": "item_code",
# 	"fieldtype": "Link",
# 	"options": "Item",
# 	"width": 180,
# },
# {
# 	"label": _("Item Name"),
# 	"fieldname": "item_name",
# 	"fieldtype": "Data",
# },
# {
# 	"label": _("Qty"),
# 	"fieldname": "qty",
# 	"fieldtype": "Float",
# },
# {
# 	"label": _("Status"),
# 	"fieldname": "status",
# 	"fieldtype": "Data",
# },
# {
# 	"label": _("Operation"),
# 	"fieldname": "operation",
# 	"fieldtype": "Link",
# 	"options": "Operation",
# },
# {
# 	"label": _("Workstation"),
# 	"fieldname": "workstation",
# 	"fieldtype": "Link",
# 	"options": "Workstation",
# },
# {
# 	"label": _("Status"),
# 	"fieldname": "job_card_status",
# 	"fieldtype": "Data"
# },
# {
# 	"label": _("Warehouse"),
# 	"fieldname": "warehouse",
# 	"fieldtype": "Link",
# 	"options": "Warehouse",
# },
# {
# 	"label": _("Company"),
# 	"fieldname": "company",
# 	"fieldtype": "Link",
# 	"options": "Company",
# },