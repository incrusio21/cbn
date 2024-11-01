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
                    if item_dict.get(d.item_code):
                        d.required_qty = item_dict.get(d.item_code).get("qty")

                    if not d.operation:
                        d.operation = operation
            else:
                for item in sorted(item_dict.values(), key=lambda d: d["idx"] or float("inf")):
                    perintah_produksi = frappe.get_cached_value("Perintah Produksi Item", {"item_group": item.item_group}, "parent")
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
                            "required_qty": item.qty,
                            "source_warehouse": item.source_warehouse or item.default_warehouse,
                            "include_item_in_manufacturing": item.include_item_in_manufacturing,
                            "custom_bom": item.bom_no,
                            "custom_perintah_produksi": perintah_produksi
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
            self.update_returned_raw_material()
    
    def update_transferred_qty_for_required_items(self):
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
                & (ste.purpose == "Material Transfer for Manufacture")
                & (ste.is_return == 0)
            )
            .groupby(ste_child.item_code)
        )

        data = query.run(as_dict=1) or []
        transferred_items = frappe._dict({d.original_item or d.item_code: d.qty for d in data})
        
        transfered_percent = []
        for row in self.required_items:
            row.db_set(
                "transferred_qty", (transferred_items.get(row.item_code) or 0.0), update_modified=False
            )
            
            transfer = row.transferred_qty if row.transferred_qty <= row.required_qty else row.required_qty
            transfered_percent.append(transfer/row.required_qty)

        if self.custom_use_perintah_produksi:
            self.db_set("material_transferred_for_manufacturing", 
                flt(min(transfered_percent) * self.qty, self.precision("material_transferred_for_manufacturing"))
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