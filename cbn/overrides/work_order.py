# Copyright (c) 2024, DAS and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import flt

from pypika import functions as fn

from erpnext.manufacturing.doctype.work_order.work_order import StockOverProductionError, WorkOrder

from cbn.cbn.custom.bom import get_bom_items_as_dict

class WorkOrder(WorkOrder):
    
    def set_required_items(self, reset_only_qty=False):
        """set required_items for production to keep track of reserved qty"""
        if not reset_only_qty:
            self.required_items = []

        operation = None
        if self.get("operations") and len(self.operations) == 1:
            operation = self.operations[0].operation

        if self.bom_no and self.qty:
            item_dict = get_bom_items_as_dict(
                self.bom_no, self.company, qty=self.qty, fetch_exploded=self.use_multi_level_bom
            )

            if reset_only_qty:
                for d in self.get("required_items"):
                    if item_dict.get((d.item_code, d.custom_perintah_produksi)):
                        perintah_produksi = frappe.get_cached_value("Perintah Produksi", d.custom_perintah_produksi, ["formula"], as_dict=1) 

                        item_qty = item_dict.get((d.item_code, d.custom_perintah_produksi)).get("qty")
                        if perintah_produksi and perintah_produksi.formula:
                            item_qty = item_qty * eval(perintah_produksi.formula)

                        d.required_qty = item_qty

                    if not d.operation:
                        d.operation = operation
            else:
                for item in sorted(item_dict.values(), key=lambda d: d["idx"] or float("inf")):
                    pp_name = item.get("perintah_produksi") or \
                        frappe.cache.hget(
                            "perintah_produksi_group:",
                            item.item_group,
                            lambda: frappe.get_value("Perintah Produksi Item", {"item_group": item.item_group}, "parent", order_by="is_default desc"),
                        )
                    
                    perintah_produksi = frappe.get_cached_value("Perintah Produksi", pp_name, ["formula"], as_dict=1) 

                    item_qty = item.qty
                    if perintah_produksi and perintah_produksi.formula:
                        item_qty = item.qty * eval(perintah_produksi.formula)

                    self.append(
                        "required_items",
                        {
                            "rate": item.rate,
                            "amount": item.rate * item.qty,
                            "operation": item.operation or operation,
                            "item_code": item.item_code,
                            "item_name": item.item_name,
                            "description": item.description,
                            "allow_alternative_item": item.allow_alternative_item,
                            "required_qty": item_qty,
                            "source_warehouse": item.source_warehouse or item.default_warehouse,
                            "include_item_in_manufacturing": item.include_item_in_manufacturing,
                            "custom_bom": item.bom_no,
                            "custom_perintah_produksi": pp_name
                        },
                    )

                    if not self.project:
                        self.project = item.get("project")

            self.set_available_qty()

    def update_required_items(self):
        """
        update bin reserved_qty_for_production
        called from Stock Entry for production, after submit, cancel
        """
        # calculate consumed qty based on submitted stock entries
        self.update_consumed_qty_for_required_items()

        if self.docstatus == 1:
            # calculate transferred qty based on submitted stock entries
            self.update_transferred_qty_for_required_items()
            self.update_returned_qty()

            # update in bin
            self.update_reserved_qty_for_production()
            self.update_converted_qty_for_production()
            self.update_returned_raw_material()
    
    def update_consumed_qty_for_required_items(self):
        """
        Update consumed qty from submitted stock entries
        against a work order for each stock item
        """

        item_consumend = {}
        precision = frappe.get_precision('Work Order Item', "consumed_qty")
        for item in self.required_items:
            # set item yang belum ada pada dict
            if not item_consumend.get(item.item_code):
                consumed_qty = frappe.db.sql("""
                     SELECT
                        SUM(detail.qty)
                    FROM
                        `tabStock Entry` entry,
                        `tabStock Entry Detail` detail
                    WHERE
                        entry.work_order = %(name)s
                            AND (entry.purpose = "Material Consumption for Manufacture"
                                OR entry.purpose = "Manufacture")
                            AND entry.docstatus = 1
                            AND detail.parent = entry.name
                            AND detail.s_warehouse IS NOT null
                            AND (detail.item_code = %(item)s
                                OR detail.original_item = %(item)s)
                    """, {"name": self.name, "item": item.item_code})[0][0] or 0.0

                item_consumend.setdefault(item.item_code, (flt(consumed_qty) or 0.0))
            
            # jika item yang d konsumsi lebih besar dari transfer maka konsumsi barang sama dengan barang yang di kirim
            item_to_consumed = item.transferred_qty if item_consumend[item.item_code] > (flt(item.transferred_qty) or 0.0) else item_consumend[item.item_code]
            item.db_set("consumed_qty", item_to_consumed, update_modified=False)

            # kurangi jumlah barang yang di konsumsi untuk item yang sama
            item_consumend[item.item_code] = flt(item_consumend[item.item_code] - (flt(item.consumed_qty) or 0.0), precision)

        for item_code, consumed in item_consumend.items():
            # memastikan tidak ada barang yang konsumsi lebih besar dari barang yang d transfer
            if (flt(consumed) or 0.0) > 0:
                frappe.throw(
                    "This transaction cannot be completed because {0} units of {1} exceed the limit of {2}.".format(
                        flt(consumed),
                        frappe.get_desk_link("Item", item_code),
                        frappe.get_desk_link("Work Order", self.name),
                    )        
                )

            # item.db_set("consumed_qty", flt(consumed_qty), update_modified=False)

    def update_converted_qty_for_production(self):
        ste = frappe.qb.DocType("Stock Entry")
        ste_child = frappe.qb.DocType("Stock Entry Detail")

        query = (
            frappe.qb.from_(ste)
            .inner_join(ste_child)
            .on(ste_child.parent == ste.name)
            .select(
                ste_child.item_code,
                ste_child.original_item,
                fn.Sum(ste_child.qty).as_("qty"),
            )
            .where(
                (ste.docstatus == 1)
                & (ste.work_order == self.name)
                & (ste_child.item_code == self.production_item)
                & (ste_child.s_warehouse.isnotnull())
                & (ste_child.t_warehouse.isnull())
                & (ste.stock_entry_type == "Manufacture Conversion")
            )
            .groupby(ste_child.item_code)
        )

        data = query.run(as_dict=1) or []
        transferred_items = frappe._dict({d.original_item or d.item_code: d.qty for d in data})
        self.db_set("custom_converted_qty", (transferred_items.get(self.production_item) or 0.0), update_modified=False)

    def update_transferred_qty_for_required_items(self):
        ste = frappe.qb.DocType("Stock Entry")
        ste_child = frappe.qb.DocType("Stock Entry Detail")

        query = (
            frappe.qb.from_(ste)
            .inner_join(ste_child)
            .on(ste_child.parent == ste.name)
            .select(
                ste.custom_perintah_produksi,
                ste_child.item_code,
                ste_child.original_item,
                fn.Sum(ste_child.qty).as_("qty"),
            )
            .where(
                (ste.docstatus == 1)
                & (ste.work_order == self.name)
                & (ste.purpose == "Material Transfer for Manufacture")
                & (ste.is_return == 0)
            )
            .groupby(ste_child.item_code, ste.custom_perintah_produksi)
        )

        data = query.run(as_dict=1) or []
        transferred_items = {}
        for d in data:
            key = (d.original_item or d.item_code, d.custom_perintah_produksi)
            transferred_items.setdefault(key, 0)
            transferred_items[key] += d.qty

        transfered_percent = []
        precision = frappe.get_precision('Work Order Item', "transferred_qty")
        for row in self.required_items:
            row.db_set(
                "transferred_qty", flt(transferred_items.get((row.item_code, row.custom_perintah_produksi)) or 0.0, precision), update_modified=False
            )

            transfer = row.transferred_qty if row.transferred_qty <= row.required_qty else row.required_qty
            transfered_percent.append(transfer/row.required_qty)

        if self.custom_use_perintah_produksi:
            min_trans = min(transfered_percent)
            adjusted_trans = 1 if min_trans > 0.9 else min_trans
            self.db_set("material_transferred_for_manufacturing", 
                flt(adjusted_trans * self.qty, self.precision("material_transferred_for_manufacturing"))
            )

    def update_returned_raw_material(self):
        ste = frappe.qb.DocType("Stock Entry")
        ste_child = frappe.qb.DocType("Stock Entry Detail")

        query = (
            frappe.qb.from_(ste)
            .inner_join(ste_child)
            .on(ste_child.parent == ste.name)
            .select(
                ste_child.item_code,
                ste_child.original_item,
                fn.Sum(ste_child.qty).as_("qty"),
            )
            .where(
                (ste.docstatus == 1)
                & (ste.work_order == self.name)
                & (ste.stock_entry_type == "Return of Remaining Goods")
            )
            .groupby(ste_child.item_code)
        )

        data = query.run(as_dict=1) or []
        transferred_items = frappe._dict({d.original_item or d.item_code: d.qty for d in data})
        for row in self.required_items:
            row.db_set(
                "custom_remaining_goods", (transferred_items.get(row.item_code) or 0.0), update_modified=False
            )

    def update_work_order_qty(self):
        """Update **Manufactured Qty** and **Material Transferred for Qty** in Work Order
        based on Stock Entry"""

        allowance_percentage = flt(
            frappe.db.get_single_value("Manufacturing Settings", "overproduction_percentage_for_work_order")
        )

        for purpose, fieldname in (
            ("Manufacture", "produced_qty"),
            ("Material Transfer for Manufacture", "material_transferred_for_manufacturing"),
        ):
            if (
                purpose == "Material Transfer for Manufacture"
                and self.operations
                and self.transfer_material_against == "Job Card"
            ):
                continue
            
            if (
                purpose == "Material Transfer for Manufacture"
                and self.custom_use_perintah_produksi
            ):
                continue
                
            qty = self.get_transferred_or_manufactured_qty(purpose)

            completed_qty = self.qty + (allowance_percentage / 100 * self.qty)
            if qty > completed_qty:
                frappe.throw(
                    _("{0} ({1}) cannot be greater than planned quantity ({2}) in Work Order {3}").format(
                        self.meta.get_label(fieldname), qty, completed_qty, self.name
                    ),
                    StockOverProductionError,
                )

            self.db_set(fieldname, qty)
            self.set_process_loss_qty()

            from erpnext.selling.doctype.sales_order.sales_order import update_produced_qty_in_so_item

            if self.sales_order and self.sales_order_item:
                update_produced_qty_in_so_item(self.sales_order, self.sales_order_item)

        if self.production_plan:
            self.set_produced_qty_for_sub_assembly_item()
            self.update_production_plan_status()

def get_doctype_map(doctype, name, filters=None, order_by=None):
	return 