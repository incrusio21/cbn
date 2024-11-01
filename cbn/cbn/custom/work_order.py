# Copyright (c) 2024, DAS and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import get_link_to_form, getdate, nowdate
from frappe.utils.data import flt

def generate_custom_field_to_space(self, method=None):
	for i in self.required_items:
		if not i.custom_diberi_gr:
			i.custom_diberi_gr = "."
		if not i.custom_diberi_pack:
			i.custom_diberi_pack = "."
		if not i.custom_petugas_gudang:
			i.custom_petugas_gudang = "."
		if not i.custom_ipc:
			i.custom_ipc = "."
		if not i.custom_prd:
			i.custom_prd = "."
		if not i.custom_keterangan:
			i.custom_keterangan = "."
	

def validate_batch_manufacture(self, method=None):
	if self.custom_is_sub_assembly or not self.custom_batch:
		return
	
	batch_mf = frappe.get_value("Batch Manufacture", self.custom_batch, ["item_code", "disabled", "status"], as_dict=1 ,for_update=1)
	if batch_mf.disabled:
		frappe.throw("Batch {} disabled".format(self.custom_batch))
	elif batch_mf.item_code != self.production_item:
		frappe.throw("Batch {} cannot be used to Item {}".format(self.custom_batch, self.production_item))
	elif batch_mf.status != "Empty":
		frappe.throw("Batch {} already {}".format(self.custom_batch, batch_mf.status))

def update_or_add_sub_assembly_batch_manufacture(self, method=None):
	if not self.custom_batch:
		return
	
	if not self.custom_is_sub_assembly:
		frappe.set_value("Batch Manufacture", self.custom_batch, "status", "Used" if self.docstatus == 1 else "Empty")
		return

	if self.docstatus == 1:
		add_sub_assembly = "add_sub_assembly"
		try:
			frappe.db.savepoint(add_sub_assembly)
			batch_manufacture = frappe.get_doc("Batch Manufacture", self.custom_batch)
			batch_manufacture.append("sub_assembly", {
				"item_code": self.production_item
			})
			batch_manufacture.flags.ignore_permissions = 1
			batch_manufacture.save()
		except frappe.UniqueValidationError:
			frappe.message_log.pop()
			frappe.db.rollback(save_point=add_sub_assembly)  # preserve transaction in postgres

def update_status_multi_level_bom(self, method=None):
	if not self.custom_is_sub_assembly:
		return
	
	if not self.custom_parent_work_order or not self.custom_parent_work_order_item:
		frappe.throw("Parent Work Order or Work Order Item not Found")

	from cbn.controllers.status_updater import update_prev_doc

	update_prev_doc(self, {
		"target_dt": 'Work Order Item',
		"target_field": "custom_work_order_qty",
		"source_dt": "Work Order",
		"source_field": "qty",
		"join_field": "custom_parent_work_order_item",
		"target_parent_dt": "Work Order",
		"target_parent_field": "custom_per_work_order",
		"target_ref_field": "required_qty",
		"percent_join_field": "custom_parent_work_order",
		"extra_parent_cond": """ and ifnull(custom_bom, "") != "" """
	})

@frappe.whitelist()
def create_work_order(work_order):
	cr_wo = []
	wo = frappe.get_doc("Work Order", work_order)
	for row in wo.required_items:
		if not row.get("custom_bom"):
			continue
		
		wo_sub_assembly = frappe.new_doc("Work Order")
		wo_sub_assembly.production_item = row.item_code
		wo_sub_assembly.bom_no = row.custom_bom
		wo_sub_assembly.qty = flt(row.required_qty - row.custom_work_order_qty)
		wo_sub_assembly.custom_batch = wo.custom_batch
		wo_sub_assembly.custom_is_sub_assembly = 1
		wo_sub_assembly.custom_parent_work_order = work_order
		wo_sub_assembly.custom_parent_work_order_item = row.name
		wo_sub_assembly.use_multi_level_bom = 0
		# wo_sub_assembly.wip_warehouse = wo.wo_sub_assembly	
		wo_sub_assembly.fg_warehouse = wo.source_warehouse

		wo_sub_assembly.get_items_and_operations_from_bom()
		wo_sub_assembly.flags.ignore_validate = 1
		wo_sub_assembly.save()
		cr_wo.append(get_link_to_form("Work Order", wo_sub_assembly.name) )
		
		cr_wo.extend(create_work_order(wo_sub_assembly.name))

	return cr_wo

@frappe.whitelist()
def create_ste_item_return(work_order_id):
	work_order = frappe.get_doc("Work Order", work_order_id)
	if not frappe.db.get_value("Warehouse", work_order.source_warehouse, "is_group"):
		source_warehouse = work_order.source_warehouse
	else:
		source_warehouse = None

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.stock_entry_type = "Return of Remaining Goods"
	stock_entry.work_order = work_order_id

	stock_entry.to_warehouse = source_warehouse
	for row in work_order.required_items:
		# hanya item dengan perintah produksi yang dapat di return yang akan muncul
		if not frappe.get_cached_value("Perintah Produksi", row.custom_perintah_produksi, "can_return") or row.custom_remaining_goods > row.transferred_qty:
			continue
		
		item_dict = {
			"item_code": row.item_code,
			"qty": flt(row.transferred_qty - row.custom_remaining_goods),
		}
		stock_entry.add_to_stock_entry_detail({row.item_code: item_dict})
		
	stock_entry.set_purpose_for_stock_entry()

	return stock_entry.as_dict()

@frappe.whitelist()
def make_stock_entry(work_order_id, purpose, qty=None, perintah_kerja=None):
	work_order = frappe.get_doc("Work Order", work_order_id)
	if not frappe.db.get_value("Warehouse", work_order.wip_warehouse, "is_group"):
		wip_warehouse = work_order.wip_warehouse
	else:
		wip_warehouse = None

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.purpose = purpose
	stock_entry.work_order = work_order_id
	stock_entry.custom_batch = work_order.custom_batch
	stock_entry.company = work_order.company
	stock_entry.from_bom = 1
	stock_entry.custom_perintah_produksi = perintah_kerja
	stock_entry.bom_no = work_order.bom_no
	stock_entry.use_multi_level_bom = work_order.use_multi_level_bom
	# accept 0 qty as well
	stock_entry.fg_completed_qty = (
		qty if qty is not None else (flt(work_order.qty) - flt(work_order.produced_qty))
	)

	if work_order.bom_no:
		stock_entry.inspection_required = frappe.db.get_value("BOM", work_order.bom_no, "inspection_required")

	if purpose == "Material Transfer for Manufacture":
		stock_entry.to_warehouse = wip_warehouse
		stock_entry.project = work_order.project
	else:
		stock_entry.from_warehouse = wip_warehouse
		stock_entry.to_warehouse = work_order.fg_warehouse
		stock_entry.project = work_order.project

	stock_entry.set_stock_entry_type()
	stock_entry.get_items()
	stock_entry.set_serial_no_batch_for_finished_good()
	return stock_entry.as_dict()