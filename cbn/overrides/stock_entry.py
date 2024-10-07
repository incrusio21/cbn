# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from collections import defaultdict

import frappe
from frappe import _

from erpnext.stock.get_item_details import (
	get_default_cost_center,
)
from frappe.utils.data import cint, cstr, flt, getdate
from erpnext.stock.doctype.item.item import get_item_defaults
from erpnext.manufacturing.doctype.bom.bom import add_additional_cost
from erpnext.stock.doctype.stock_entry.stock_entry import FinishedGoodError, StockEntry, get_available_materials

class StockEntry(StockEntry):
    
    def validate_batch(self):
        if self.purpose in [
            "Material Transfer for Manufacture",
            "Manufacture",
            "Repack",
            "Send to Subcontractor",
        ]:
            for item in self.get("items"):
                if item.batch_no:
                    disabled = frappe.db.get_value("Batch", item.batch_no, "disabled")
                    if disabled == 0:
                        expiry_date = frappe.db.get_value("Batch", item.batch_no, "expiry_date")
                        if expiry_date:
                            if getdate(self.posting_date) > getdate(expiry_date):
                                frappe.throw(
                                    _("Batch {0} of Item {1} has expired.").format(
                                        item.batch_no, item.item_code
                                    )
                                )
                    else:
                        frappe.throw(
                            _("Batch {0} of Item {1} is disabled.").format(item.batch_no, item.item_code)
                        )

                if item.custom_batch and self.custom_batch and item.custom_batch != self.custom_batch:
                    frappe.throw(
                        _("Batch on #Row{} doesn't match the batch on the Work Order {}").format(item.idx, self.work_order)
                    )

    def get_sle_for_source_warehouse(self, sl_entries, finished_item_row):
        for d in self.get("items"):
            if cstr(d.s_warehouse):
                if d.serial_and_batch_bundle and self.docstatus == 1:
                    self.validate_serial_batch_bundle_type(d.serial_and_batch_bundle)

                sle = self.get_sl_entries(
                    d,
                    {
                        "warehouse": cstr(d.s_warehouse),
                        "actual_qty": -flt(d.transfer_qty),
                        "incoming_rate": 0,
                        "custom_batch": d.custom_batch
                    },
                )
                if cstr(d.t_warehouse):
                    sle.dependant_sle_voucher_detail_no = d.name
                elif finished_item_row and (
                    finished_item_row.item_code != d.item_code
                    or finished_item_row.t_warehouse != d.s_warehouse
                ):
                    sle.dependant_sle_voucher_detail_no = finished_item_row.name

                if sle.serial_and_batch_bundle and self.docstatus == 2:
                    bundle_id = frappe.get_cached_value(
                        "Serial and Batch Bundle",
                        {
                            "voucher_detail_no": d.name,
                            "voucher_no": self.name,
                            "is_cancelled": 0,
                            "type_of_transaction": "Outward",
                        },
                        "name",
                    )

                    if bundle_id:
                        sle.serial_and_batch_bundle = bundle_id
                
                sl_entries.append(sle)

    def get_sle_for_target_warehouse(self, sl_entries, finished_item_row):
        for d in self.get("items"):
            if cstr(d.t_warehouse):
                sle = self.get_sl_entries(
                    d,
                    {
                        "warehouse": cstr(d.t_warehouse),
                        "actual_qty": flt(d.transfer_qty),
                        "incoming_rate": flt(d.valuation_rate),
                        "custom_batch": d.custom_batch
                    },
                )

                if cstr(d.s_warehouse) or (finished_item_row and d.name == finished_item_row.name):
                    sle.recalculate_rate = 1

                allowed_types = [
                    "Material Transfer",
                    "Send to Subcontractor",
                    "Material Transfer for Manufacture",
                ]

                if self.purpose in allowed_types and d.serial_and_batch_bundle and self.docstatus == 1:
                    sle.serial_and_batch_bundle = self.make_package_for_transfer(
                        d.serial_and_batch_bundle, d.t_warehouse
                    )

                if sle.serial_and_batch_bundle and self.docstatus == 2:
                    bundle_id = frappe.get_cached_value(
                        "Serial and Batch Bundle",
                        {
                            "voucher_detail_no": d.name,
                            "voucher_no": self.name,
                            "is_cancelled": 0,
                            "type_of_transaction": "Inward",
                        },
                        "name",
                    )

                    if sle.serial_and_batch_bundle != bundle_id:
                        sle.serial_and_batch_bundle = bundle_id

                sl_entries.append(sle)
                                                
    def get_pending_raw_materials(self, backflush_based_on=None):
        """
        issue (item quantity) that is pending to issue or desire to transfer,
        whichever is less
        """
        item_dict = self.get_pro_order_required_items(backflush_based_on)

        max_qty = flt(self.pro_doc.qty)

        allow_overproduction = False
        overproduction_percentage = flt(
            frappe.db.get_single_value("Manufacturing Settings", "overproduction_percentage_for_work_order")
        )

        to_transfer_qty = flt(self.pro_doc.material_transferred_for_manufacturing) + flt(
            self.fg_completed_qty
        )
        transfer_limit_qty = max_qty + ((max_qty * overproduction_percentage) / 100)

        if transfer_limit_qty >= to_transfer_qty:
            allow_overproduction = True

        for item, item_details in item_dict.items():
            pending_to_issue = flt(item_details.required_qty) - flt(item_details.transferred_qty)
            desire_to_transfer = flt(self.fg_completed_qty) * flt(item_details.required_qty) / max_qty

            if (
                desire_to_transfer <= pending_to_issue
                or (desire_to_transfer > 0 and backflush_based_on == "Material Transferred for Manufacture")
                or allow_overproduction
            ):
                # "No need for transfer but qty still pending to transfer" case can occur
                # when transferring multiple RM in different Stock Entries
                item_dict[item]["qty"] = desire_to_transfer if (desire_to_transfer > 0) else pending_to_issue
            elif pending_to_issue > 0:
                item_dict[item]["qty"] = pending_to_issue
            else:
                item_dict[item]["qty"] = 0

        # delete items with 0 qty
        list_of_items = list(item_dict.keys())
        for item in list_of_items:
            if not item_dict[item]["qty"]:
                del item_dict[item]

        # show some message
        if not len(item_dict):
            frappe.msgprint(_("""All items have already been transferred for this Work Order."""))

        return item_dict
                            
    def load_items_from_bom(self):
        custom_batch = None
        if self.work_order:
            item_code = self.pro_doc.production_item
            to_warehouse = self.pro_doc.fg_warehouse
            custom_batch = self.pro_doc.custom_batch
        else:
            item_code = frappe.db.get_value("BOM", self.bom_no, "item")
            to_warehouse = self.to_warehouse

        item = get_item_defaults(item_code, self.company)

        if not self.work_order and not to_warehouse:
            # in case of BOM
            to_warehouse = item.get("default_warehouse")

        args = {
            "to_warehouse": to_warehouse,
            "from_warehouse": "",
            "qty": flt(self.fg_completed_qty) - flt(self.process_loss_qty),
            "item_name": item.item_name,
            "description": item.description,
            "stock_uom": item.stock_uom,
            "expense_account": item.get("expense_account"),
            "cost_center": item.get("buying_cost_center"),
            "is_finished_item": 1,
            "custom_batch": custom_batch
        }


        if (
            self.work_order
            and self.pro_doc.has_batch_no
            and not self.pro_doc.has_serial_no
            and cint(
                frappe.db.get_single_value(
                    "Manufacturing Settings", "make_serial_no_batch_from_work_order", cache=True
                )
            )
        ):
            self.set_batchwise_finished_goods(args, item)
        else:
            self.add_finished_goods(args, item)

    def get_pro_order_required_items(self, backflush_based_on=None):
        """
        Gets Work Order Required Items only if Stock Entry purpose is **Material Transferred for Manufacture**.
        """
        item_dict, job_card_items = frappe._dict(), []
        work_order = frappe.get_doc("Work Order", self.work_order)

        consider_job_card = work_order.transfer_material_against == "Job Card" and self.get("job_card")
        if consider_job_card:
            job_card_items = self.get_job_card_item_codes(self.get("job_card"))

        if not frappe.db.get_value("Warehouse", work_order.wip_warehouse, "is_group"):
            wip_warehouse = work_order.wip_warehouse
        else:
            wip_warehouse = None

        for d in work_order.get("required_items"):
            if consider_job_card and (d.item_code not in job_card_items):
                continue

            transfer_pending = flt(d.required_qty) > flt(d.transferred_qty)
            can_transfer = transfer_pending or (backflush_based_on == "Material Transferred for Manufacture")

            if not can_transfer:
                continue

            if d.include_item_in_manufacturing:
                item_row = d.as_dict()
                item_row["idx"] = len(item_dict) + 1

                if consider_job_card:
                    job_card_item = frappe.db.get_value(
                        "Job Card Item", {"item_code": d.item_code, "parent": self.get("job_card")}
                    )
                    item_row["job_card_item"] = job_card_item or None

                if d.source_warehouse and not frappe.db.get_value(
                    "Warehouse", d.source_warehouse, "is_group"
                ):
                    item_row["from_warehouse"] = d.source_warehouse

                item_row["to_warehouse"] = wip_warehouse
                if item_row["allow_alternative_item"]:
                    item_row["allow_alternative_item"] = work_order.allow_alternative_item

                if d.custom_bom:
                    item_row["custom_batch"] = work_order.custom_batch

                item_dict.setdefault(d.item_code, item_row)

        return item_dict
    
    def add_to_stock_entry_detail(self, item_dict, bom_no=None):
        precision = frappe.get_precision("Stock Entry Detail", "qty")
        for d in item_dict:
            item_row = item_dict[d]

            child_qty = flt(item_row["qty"], precision)
            if not self.is_return and child_qty <= 0:
                continue

            se_child = self.append("items")
            stock_uom = item_row.get("stock_uom") or frappe.db.get_value("Item", d, "stock_uom")
            se_child.s_warehouse = item_row.get("from_warehouse")
            se_child.t_warehouse = item_row.get("to_warehouse")
            se_child.item_code = item_row.get("item_code") or cstr(d)
            se_child.uom = item_row["uom"] if item_row.get("uom") else stock_uom
            se_child.stock_uom = stock_uom
            se_child.qty = child_qty
            se_child.allow_alternative_item = item_row.get("allow_alternative_item", 0)
            se_child.subcontracted_item = item_row.get("main_item_code")
            se_child.cost_center = item_row.get("cost_center") or get_default_cost_center(
                item_row, company=self.company
            )
            se_child.is_finished_item = item_row.get("is_finished_item", 0)
            se_child.is_scrap_item = item_row.get("is_scrap_item", 0)
            se_child.po_detail = item_row.get("po_detail")
            se_child.sco_rm_detail = item_row.get("sco_rm_detail")

            for field in [
                self.subcontract_data.rm_detail_field,
                "original_item",
                "expense_account",
                "description",
                "item_name",
                "serial_and_batch_bundle",
                "allow_zero_valuation_rate",
                "use_serial_batch_fields",
                "batch_no",
                "serial_no",
                "custom_batch"
            ]:
                if item_row.get(field):
                    se_child.set(field, item_row.get(field))

            if se_child.s_warehouse is None:
                se_child.s_warehouse = self.from_warehouse
            if se_child.t_warehouse is None:
                se_child.t_warehouse = self.to_warehouse

            # in stock uom
            se_child.conversion_factor = flt(item_row.get("conversion_factor")) or 1
            se_child.transfer_qty = flt(
                item_row["qty"] * se_child.conversion_factor, se_child.precision("qty")
            )

            se_child.bom_no = bom_no  # to be assigned for finished item
            se_child.job_card_item = item_row.get("job_card_item") if self.get("job_card") else None