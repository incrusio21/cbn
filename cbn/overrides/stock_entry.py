# Copyright (c) 2024, DAS and Contributors
# License: GNU General Public License v3. See license.txt

from collections import defaultdict
from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos
from pypika import functions as fn

import frappe
from frappe import _

from erpnext.stock.get_item_details import (
	get_default_cost_center,
)
from frappe.utils.data import cint, cstr, flt, getdate
from erpnext.stock.doctype.item.item import get_item_defaults
from erpnext.manufacturing.doctype.bom.bom import add_additional_cost
from erpnext.stock.doctype.stock_entry.stock_entry import FinishedGoodError, StockEntry, create_serial_and_batch_bundle

class StockEntry(StockEntry):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from erpnext.stock.doctype.landed_cost_taxes_and_charges.landed_cost_taxes_and_charges import LandedCostTaxesandCharges
        from erpnext.stock.doctype.stock_entry_detail.stock_entry_detail import StockEntryDetail
        from frappe.types import DF

        add_to_transit: DF.Check
        additional_costs: DF.Table[LandedCostTaxesandCharges]
        address_display: DF.SmallText | None
        amended_from: DF.Link | None
        apply_putaway_rule: DF.Check
        asset_repair: DF.Link | None
        bom_no: DF.Link | None
        company: DF.Link
        credit_note: DF.Link | None
        delivery_note_no: DF.Link | None
        fg_completed_qty: DF.Float
        from_bom: DF.Check
        from_warehouse: DF.Link | None
        inspection_required: DF.Check
        is_opening: DF.Literal["No", "Yes"]
        is_return: DF.Check
        items: DF.Table[StockEntryDetail]
        job_card: DF.Link | None
        letter_head: DF.Link | None
        naming_series: DF.Literal["MAT-STE-.YYYY.-"]
        outgoing_stock_entry: DF.Link | None
        per_transferred: DF.Percent
        pick_list: DF.Link | None
        posting_date: DF.Date | None
        posting_time: DF.Time | None
        process_loss_percentage: DF.Percent
        process_loss_qty: DF.Float
        project: DF.Link | None
        purchase_order: DF.Link | None
        purchase_receipt_no: DF.Link | None
        purpose: DF.Literal["Material Issue", "Material Receipt", "Material Transfer", "Material Transfer for Manufacture", "Material Consumption for Manufacture", "Manufacture", "Repack", "Send to Subcontractor", "Disassemble"]
        remarks: DF.Text | None
        sales_invoice_no: DF.Link | None
        scan_barcode: DF.Data | None
        select_print_heading: DF.Link | None
        set_posting_time: DF.Check
        source_address_display: DF.SmallText | None
        source_warehouse_address: DF.Link | None
        stock_entry_type: DF.Link
        subcontracting_order: DF.Link | None
        supplier: DF.Link | None
        supplier_address: DF.Link | None
        supplier_name: DF.Data | None
        target_address_display: DF.SmallText | None
        target_warehouse_address: DF.Link | None
        to_warehouse: DF.Link | None
        total_additional_costs: DF.Currency
        total_amount: DF.Currency
        total_incoming_value: DF.Currency
        total_outgoing_value: DF.Currency
        use_multi_level_bom: DF.Check
        value_difference: DF.Currency
        work_order: DF.Link | None
    # end: auto-generated types
    
    def on_update(self):
        self.validate_work_order_transferred_qty_for_required_items()

    def before_submit(self):
        self.set_raw_material_loss()
        self.update_or_add_conversion_batch_manufacture()

    def set_raw_material_loss(self):
        if self.stock_entry_type not in ["Manufacture"] or not self.process_loss_qty:
            return

        precision = frappe.get_precision("Stock Entry Detail", "qty")
        # get qty item per loss qty
        items = {}
        for bom in frappe.get_all("BOM Item", 
            filters={"parent": self.bom_no}, fields=["item_code", "qty"]):
            items.setdefault(bom.item_code, flt(bom.qty * self.process_loss_qty, precision))
        
        loss_items = {}
        removed_item = []
        for d in self.items:
            if not frappe.get_cached_value("Perintah Produksi", d.perintah_produksi, "goods_can_be_loss"):
                continue
            
            key = (d.original_item or d.item_code, d.perintah_produksi)
            loss_items.setdefault(key, 0)
            process_loss_qty = items.get((d.original_item or d.item_code))
            if not process_loss_qty:
                frappe.throw("Item {} is not listed in the Bill of Materials {}".format((d.original_item or d.item_code), self.bom_no))
                
            if flt(loss_items[key], precision) >= process_loss_qty:
                continue
            
            item = d.as_dict(no_default_fields=True).copy()
            loss_qty = flt(process_loss_qty - loss_items[key], precision)
            if d.qty <= loss_qty:
                removed_item.append(d)
            else:
                item.update({"qty": loss_qty, "item_detail": d.name})
                d.qty = flt(d.qty - loss_qty, precision)

            loss_items[key] += loss_qty
            self.append("loss_items", item)

        for r in removed_item:
            self.remove(r)

        self.set_missing_values()

    def update_or_add_conversion_batch_manufacture(self):
        if self.stock_entry_type not in ["Manufacture Conversion"] or not self.custom_batch:
            return

        for item in self.get("items"):
            if item.is_finished_item:
                add_conversion = "add_conversion"
                try:
                    frappe.db.savepoint(add_conversion)
                    batch_manufacture = frappe.get_doc("Batch Manufacture", item.custom_batch)
                    batch_manufacture.append("item_conversion", {
                        "item_code": item.item_code
                    })
                    batch_manufacture.flags.ignore_permissions = 1
                    batch_manufacture.save()
                except frappe.UniqueValidationError:
                    frappe.message_log.pop()
                    frappe.db.rollback(save_point=add_conversion)

    def validate_work_order_transferred_qty_for_required_items(self):
        if self.purpose not in (
            "Material Transfer for Manufacture",
        ):
            return
        
        # ste = frappe.qb.DocType("Stock Entry")
        # ste_child = frappe.qb.DocType("Stock Entry Detail")

        items = frappe.get_all("Work Order Item", filters={"parent": self.work_order }, pluck="item_code")
                         
        # item_list = {}
        for d in self.items:
            key = d.original_item or d.item_code
            if key not in items:
                frappe.throw(
                    "This transaction cannot be completed because Item {0} not in Work Order {1}.".format(
                        frappe.get_desk_link("Item", key),
                        frappe.get_desk_link("Work Order", self.work_order),
                    )        
                )
            # item_list.setdefault(key, frappe.get_value("Work Order Item", {"parent": self.work_order, "item_code": key }, "required_qty") or 0.0)

        # query = (
        #     frappe.qb.from_(ste)
        #     .inner_join(ste_child)
        #     .on(ste_child.parent == ste.name)
        #     .select(
        #         ste_child.item_code,
        #         ste_child.original_item,
        #         fn.Sum(ste_child.qty).as_("qty"),
        #     )
        #     .where(
        #         (ste.docstatus < 2)
        #         & (ste.work_order == self.work_order)
        #         & (ste.purpose == "Material Transfer for Manufacture")
        #         & (ste.is_return == 0)
        #     )
        #     .groupby(ste_child.item_code)
        # )

        # data = query.run(as_dict=1) or []
        # transferred_items = frappe._dict({d.original_item or d.item_code: d.qty for d in data})
        
        # for item_code, qty in item_list.items(): 
        #     if (transferred_items.get(item_code) or 0.0) > qty:
        #         frappe.throw(
        #             "This transaction cannot be completed because {0} units of {1} exceed the limit of {2}.".format(
        #                 flt(transferred_items.get(item_code) - qty),
        #                 frappe.get_desk_link("Item", item_code),
        #                 frappe.get_desk_link("Work Order", self.work_order),
        #             )        
        #         )

    def validate_fg_completed_qty(self):
        item_wise_qty = {}
        if self.purpose == "Manufacture" and self.work_order:
            for d in self.items:
                if d.is_finished_item:
                    if self.process_loss_qty:
                        d.qty = self.fg_completed_qty - self.process_loss_qty

                    item_wise_qty.setdefault(d.item_code, []).append(d.qty)

        precision = frappe.get_precision("Stock Entry Detail", "qty")
        for item_code, qty_list in item_wise_qty.items():
            total = flt(sum(qty_list), precision)

            if (self.fg_completed_qty - total) > 0 and not self.process_loss_qty:
                self.process_loss_qty = flt(self.fg_completed_qty - total, precision)
                self.process_loss_percentage = flt(self.process_loss_qty * 100 / self.fg_completed_qty)

            if self.process_loss_qty:
                total = flt(total + self.process_loss_qty, precision)

            if self.fg_completed_qty != total:
                frappe.throw(
                    _(
                        "The finished product {0} quantity {1} and For Quantity {2} cannot be different"
                    ).format(frappe.bold(item_code), frappe.bold(total), frappe.bold(self.fg_completed_qty))
                )

    def validate_work_order(self):
        if self.purpose in (
            "Manufacture",
            "Material Transfer for Manufacture",
            "Material Consumption for Manufacture",
        ):
            # check if work order is entered

            if (
                self.purpose == "Manufacture" or self.purpose == "Material Consumption for Manufacture"
            ) and self.work_order:
                if not self.fg_completed_qty:
                    frappe.throw(_("For Quantity (Manufactured Qty) is mandatory"))
                self.check_if_operations_completed()
                self.check_duplicate_entry_for_work_order()
        elif self.purpose != "Material Transfer" and \
            self.stock_entry_type not in ("Return of Remaining Goods", "Manufacture Conversion", "BK Pengganti Reject", "BK Reject", "BK Sisa"):
            self.work_order = None

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

    def validate_finished_goods(self):
        """
        1. Check if FG exists (mfg, repack)
        2. Check if Multiple FG Items are present (mfg)
        3. Check FG Item and Qty against WO if present (mfg)
        """
        production_item, wo_qty, finished_items = None, 0, []

        wo_details = frappe.db.get_value("Work Order", self.work_order, ["production_item", "qty"])
        if wo_details:
            production_item, wo_qty = wo_details

        for d in self.get("items"):
            if d.is_finished_item:
                if not self.work_order or self.stock_entry_type in ("Manufacture Conversion"):
                    # Independent MFG Entry/ Repack Entry, no WO to match against
                    finished_items.append(d.item_code)
                    continue

                if d.item_code != production_item:
                    frappe.throw(
                        _("Finished Item {0} does not match with Work Order {1}").format(
                            d.item_code, self.work_order
                        )
                    )
                elif flt(d.transfer_qty) > flt(self.fg_completed_qty):
                    frappe.throw(
                        _("Quantity in row {0} ({1}) must be same as manufactured quantity {2}").format(
                            d.idx, d.transfer_qty, self.fg_completed_qty
                        )
                    )

                finished_items.append(d.item_code)

        if not finished_items:
            frappe.throw(
                msg=_("There must be atleast 1 Finished Good in this Stock Entry").format(self.name),
                title=_("Missing Finished Good"),
                exc=FinishedGoodError,
            )

        if self.purpose == "Manufacture":
            if len(set(finished_items)) > 1:
                frappe.throw(
                    msg=_("Multiple items cannot be marked as finished item"),
                    title=_("Note"),
                    exc=FinishedGoodError,
                )

            allowance_percentage = flt(
                frappe.db.get_single_value(
                    "Manufacturing Settings", "overproduction_percentage_for_work_order"
                )
            )
            allowed_qty = wo_qty + ((allowance_percentage / 100) * wo_qty)

            # No work order could mean independent Manufacture entry, if so skip validation
            if self.work_order and self.fg_completed_qty > allowed_qty:
                frappe.throw(
                    _("For quantity {0} should not be greater than allowed quantity {1}").format(
                        flt(self.fg_completed_qty), allowed_qty
                    )
                )

    def set_process_loss_qty(self):
        if self.purpose not in ("Manufacture", "Repack") or self.stock_entry_type in ["Manufacture Conversion"]:
            return

        precision = self.precision("process_loss_qty")
        if self.work_order:
            data = frappe.get_all(
                "Work Order Operation",
                filters={"parent": self.work_order},
                fields=["max(process_loss_qty) as process_loss_qty"],
            )

            if data and data[0].process_loss_qty is not None:
                process_loss_qty = data[0].process_loss_qty
                if flt(self.process_loss_qty, precision) != flt(process_loss_qty, precision):
                    self.process_loss_qty = flt(process_loss_qty - (self.pro_doc.get("process_loss_qty") or 0), precision)

                    frappe.msgprint(
                        _("The Process Loss Qty has reset as per job cards Process Loss Qty"), alert=True
                    )

        if not self.process_loss_percentage and not self.process_loss_qty:
            self.process_loss_percentage = frappe.get_cached_value(
                "BOM", self.bom_no, "process_loss_percentage"
            )

        if self.process_loss_percentage and not self.process_loss_qty:
            self.process_loss_qty = flt(
                (flt(self.fg_completed_qty) * flt(self.process_loss_percentage)) / 100
            )
        elif self.process_loss_qty and not self.process_loss_percentage:
            self.process_loss_percentage = flt(
                (flt(self.process_loss_qty) / flt(self.fg_completed_qty)) * 100
            )

    @frappe.whitelist()
    def get_items(self):
        self.set("items", [])
        self.validate_work_order()

        if self.purpose == "Disassemble":
            return self.get_items_for_disassembly()

        if not self.posting_date or not self.posting_time:
            frappe.throw(_("Posting date and posting time is mandatory"))

        self.set_work_order_details()
        self.flags.backflush_based_on = frappe.db.get_single_value(
            "Manufacturing Settings", "backflush_raw_materials_based_on"
        )

        if self.bom_no:
            backflush_based_on = frappe.db.get_single_value(
                "Manufacturing Settings", "backflush_raw_materials_based_on"
            )

            if self.purpose in [
                "Material Issue",
                "Material Transfer",
                "Manufacture",
                "Repack",
                "Send to Subcontractor",
                "Material Transfer for Manufacture",
                "Material Consumption for Manufacture",
            ]:
                if self.work_order and self.purpose == "Material Transfer for Manufacture":
                    item_dict = self.get_pending_raw_materials(backflush_based_on)
                    if self.to_warehouse and self.pro_doc:
                        for item in item_dict.values():
                            item["to_warehouse"] = self.pro_doc.wip_warehouse
                    self.add_to_stock_entry_detail(item_dict)

                elif (
                    self.work_order
                    and (
                        self.purpose == "Manufacture"
                        or self.purpose == "Material Consumption for Manufacture"
                    )
                    and not self.pro_doc.skip_transfer
                    and self.flags.backflush_based_on == "Material Transferred for Manufacture"
                ):
                    self.add_transfered_raw_materials_in_items()

                elif (
                    self.work_order
                    and (
                        self.purpose == "Manufacture"
                        or self.purpose == "Material Consumption for Manufacture"
                    )
                    and self.flags.backflush_based_on == "BOM"
                    and frappe.db.get_single_value("Manufacturing Settings", "material_consumption") == 1
                ):
                    self.get_unconsumed_raw_materials()

                elif (
                    self.work_order
                    and self.stock_entry_type == "Material Transfer Loss"
                    and not self.pro_doc.skip_transfer
                    and self.flags.backflush_based_on == "Material Transferred for Manufacture"
                ):
                    self.add_transfered_losss_materials_in_items()
                else:
                    if not self.fg_completed_qty:
                        frappe.throw(_("Manufacturing Quantity is mandatory"))

                    item_dict = self.get_bom_raw_materials(self.fg_completed_qty)

                    # Get Subcontract Order Supplied Items Details
                    if (
                        self.get(self.subcontract_data.order_field)
                        and self.purpose == "Send to Subcontractor"
                    ):
                        # Get Subcontract Order Supplied Items Details
                        parent = frappe.qb.DocType(self.subcontract_data.order_doctype)
                        child = frappe.qb.DocType(self.subcontract_data.order_supplied_items_field)

                        item_wh = (
                            frappe.qb.from_(parent)
                            .inner_join(child)
                            .on(parent.name == child.parent)
                            .select(child.rm_item_code, child.reserve_warehouse)
                            .where(parent.name == self.get(self.subcontract_data.order_field))
                        ).run(as_list=True)

                        item_wh = frappe._dict(item_wh)

                    for item in item_dict.values():
                        if self.pro_doc and cint(self.pro_doc.from_wip_warehouse):
                            item["from_warehouse"] = self.pro_doc.wip_warehouse
                        # Get Reserve Warehouse from Subcontract Order
                        if (
                            self.get(self.subcontract_data.order_field)
                            and self.purpose == "Send to Subcontractor"
                        ):
                            item["from_warehouse"] = item_wh.get(item.item_code)
                        item["to_warehouse"] = (
                            self.to_warehouse if self.purpose == "Send to Subcontractor" else ""
                        )

                    self.add_to_stock_entry_detail(item_dict)

            # fetch the serial_no of the first stock entry for the second stock entry
            if self.work_order and self.purpose == "Manufacture":
                work_order = frappe.get_doc("Work Order", self.work_order)
                add_additional_cost(self, work_order)

            # add finished goods item
            if self.purpose in ("Manufacture", "Repack"):
                self.set_process_loss_qty()
                self.load_items_from_bom()

        self.set_scrap_items()
        self.set_actual_qty()
        self.validate_customer_provided_item()
        self.calculate_rate_and_amount(raise_error_if_no_rate=False)
    
    def add_transfered_raw_materials_in_items(self) -> None:
        available_materials = get_available_materials(self.work_order)

        wo_data = frappe.db.get_value(
            "Work Order",
            self.work_order,
            ["qty", "produced_qty", "material_transferred_for_manufacturing as trans_qty", "process_loss_qty"],
            as_dict=1,
        )

        precision = frappe.get_precision("Stock Entry Detail", "qty")
        for _key, row in available_materials.items():
            remaining_qty_to_produce = flt(wo_data.trans_qty) - flt(wo_data.produced_qty) - flt(wo_data.process_loss_qty)
            if remaining_qty_to_produce <= 0 and not self.is_return:
                continue
                
            qty = flt(row.qty)
            if not self.is_return:
                qty = (flt(row.qty) * flt(self.fg_completed_qty)) / remaining_qty_to_produce

            item = row.item_details
            if cint(frappe.get_cached_value("UOM", item.stock_uom, "must_be_whole_number")):
                qty = frappe.utils.ceil(qty)

            if row.batch_details:
                row.batches_to_be_consume = defaultdict(float)
                batches = row.batch_details
                self.update_batches_to_be_consume(batches, row, qty)

            elif row.serial_nos:
                serial_nos = row.serial_nos[0 : cint(qty)]
                row.serial_nos = serial_nos

            item.perintah_produksi = row.perintah_produksi
            
            if flt(qty, precision) != 0.0:
                self.update_item_in_stock_entry_detail(row, item, qty)

    def add_transfered_losss_materials_in_items(self) -> None:
        available_materials = get_available_materials(self.work_order)

        wo_data = frappe.db.get_value(
            "Work Order",
            self.work_order,
            ["qty", "produced_qty", "material_transferred_for_manufacturing as trans_qty"],
            as_dict=1,
        )

        precision = frappe.get_precision("Stock Entry Detail", "qty")
        for _key, row in available_materials.items():
            remaining_qty_to_produce = flt(wo_data.trans_qty) - flt(wo_data.produced_qty)
            if remaining_qty_to_produce <= 0 and not self.is_return:
                continue

            qty = flt(row.qty)
            if not self.is_return:
                qty = (flt(row.qty) * flt(self.fg_completed_qty)) / remaining_qty_to_produce

            item = row.item_details
            if cint(frappe.get_cached_value("UOM", item.stock_uom, "must_be_whole_number")):
                qty = frappe.utils.ceil(qty)

            if row.batch_details:
                row.batches_to_be_consume = defaultdict(float)
                batches = row.batch_details
                self.update_batches_to_be_consume(batches, row, qty)

            elif row.serial_nos:
                serial_nos = row.serial_nos[0 : cint(qty)]
                row.serial_nos = serial_nos

            item.perintah_produksi = row.perintah_produksi
            if flt(qty, precision) != 0.0:
                self.update_item_in_stock_entry_detail(row, item, qty)

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

    def get_unconsumed_raw_materials(self):
        wo = frappe.get_doc("Work Order", self.work_order)
        wo_items = frappe.get_all(
            "Work Order Item",
            filters={"parent": self.work_order},
            fields=["name", "item_code", "source_warehouse", "required_qty", "consumed_qty", "transferred_qty"],
        )

        work_order_qty = wo.material_transferred_for_manufacturing or wo.qty
        for item in wo_items:
            item_account_details = get_item_defaults(item.item_code, self.company)
            # Take into account consumption if there are any.

            wo_item_qty = item.transferred_qty or item.required_qty

            wo_qty_consumed = flt(wo_item_qty) - flt(item.consumed_qty)
            wo_qty_to_produce = flt(work_order_qty) - flt(wo.produced_qty)

            req_qty_each = (wo_qty_consumed) / (wo_qty_to_produce or 1)

            qty = req_qty_each * flt(self.fg_completed_qty)

            if qty > 0:
                self.add_to_stock_entry_detail(
                    {
                        item.item_code: {
                            "from_warehouse": wo.wip_warehouse or item.source_warehouse,
                            "to_warehouse": "",
                            "qty": qty,
                            "item_name": item.item_name,
                            "description": item.description,
                            "stock_uom": item_account_details.stock_uom,
                            "expense_account": item_account_details.get("expense_account"),
                            "cost_center": item_account_details.get("buying_cost_center"),
                            "wo_detail": item.name
                        }
                    }
                )

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
        consider_perintah_produksi = self.get("custom_perintah_produksi")
        if consider_job_card:
            job_card_items = self.get_job_card_item_codes(self.get("job_card"))

        if not frappe.db.get_value("Warehouse", work_order.wip_warehouse, "is_group"):
            wip_warehouse = work_order.wip_warehouse
        else:
            wip_warehouse = None

        for d in work_order.get("required_items"):
            if consider_job_card and (d.item_code not in job_card_items):
                continue
            
            if consider_perintah_produksi and d.custom_perintah_produksi != consider_perintah_produksi:
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
    
    def update_item_in_stock_entry_detail(self, row, item, qty) -> None:
        if not qty:
            return

        use_serial_batch_fields = frappe.db.get_single_value("Stock Settings", "use_serial_batch_fields")
        ste_item_details = {
            "from_warehouse": item.warehouse,
            "to_warehouse": "",
            "qty": qty,
            "item_name": item.item_name,
            "serial_and_batch_bundle": create_serial_and_batch_bundle(self, row, item, "Outward")
            if not use_serial_batch_fields
            else "",
            "description": item.description,
            "stock_uom": item.stock_uom,
            "expense_account": item.expense_account,
            "cost_center": item.buying_cost_center,
            "original_item": item.original_item,
            "custom_batch": item.custom_batch,
            "perintah_produksi": item.get("perintah_produksi"),
            "serial_no": "\n".join(row.serial_nos)
            if row.serial_nos and not row.batches_to_be_consume
            else "",
            "use_serial_batch_fields": use_serial_batch_fields,
        }

        if self.is_return:
            ste_item_details["to_warehouse"] = item.s_warehouse

        if use_serial_batch_fields and not row.serial_no and row.batches_to_be_consume:
            for batch_no, batch_qty in row.batches_to_be_consume.items():
                ste_item_details.update(
                    {
                        "batch_no": batch_no,
                        "qty": batch_qty,
                    }
                )

                self.add_to_stock_entry_detail({item.item_code: ste_item_details})
        else:
            self.add_to_stock_entry_detail({item.item_code: ste_item_details})

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
                "custom_batch",
                "perintah_produksi",
                "wo_detail"
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

def get_available_materials(work_order) -> dict:
    data = get_stock_entry_data(work_order)

    available_materials = {}
    for row in data:
        key = (row.item_code, row.warehouse)
        if row.purpose != "Material Transfer for Manufacture":
            key = (row.item_code, row.s_warehouse)

        if key not in available_materials:
            available_materials.setdefault(
                key,
                frappe._dict(
                    {"item_details": row, "perintah_produksi": "", "batch_details": defaultdict(float), "qty": 0, "serial_nos": []}
                ),
            )

        item_data = available_materials[key]

        if row.purpose == "Material Transfer for Manufacture":
            item_data.qty += row.qty
            if row.batch_no:
                item_data.batch_details[row.batch_no] += row.qty

            elif row.batch_nos:
                for batch_no, qty in row.batch_nos.items():
                    item_data.batch_details[batch_no] += qty

            if row.serial_no:
                item_data.serial_nos.extend(get_serial_nos(row.serial_no))
                item_data.serial_nos.sort()

            elif row.serial_nos:
                item_data.serial_nos.extend(get_serial_nos(row.serial_nos))
                item_data.serial_nos.sort()

            item_data.perintah_produksi = row.perintah_produksi
        else:
            # Consume raw material qty in case of 'Manufacture' or 'Material Consumption for Manufacture'

            item_data.qty -= row.qty
            if row.batch_no:
                item_data.batch_details[row.batch_no] -= row.qty

            elif row.batch_nos:
                for batch_no, qty in row.batch_nos.items():
                    item_data.batch_details[batch_no] += qty

            if row.serial_no:
                for serial_no in get_serial_nos(row.serial_no):
                    if serial_no in item_data.serial_nos:
                        item_data.serial_nos.remove(serial_no)

            elif row.serial_nos:
                for serial_no in get_serial_nos(row.serial_nos):
                    if serial_no in item_data.serial_nos:
                        item_data.serial_nos.remove(serial_no)

    return available_materials

def get_stock_entry_data(work_order):
    from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
        get_voucher_wise_serial_batch_from_bundle,
    )

    stock_entry = frappe.qb.DocType("Stock Entry")
    stock_entry_detail = frappe.qb.DocType("Stock Entry Detail")

    data = (
        frappe.qb.from_(stock_entry)
        .from_(stock_entry_detail)
        .select(
            stock_entry_detail.item_name,
            stock_entry_detail.original_item,
            stock_entry_detail.item_code,
            stock_entry_detail.qty,
            (stock_entry_detail.t_warehouse).as_("warehouse"),
            (stock_entry_detail.s_warehouse).as_("s_warehouse"),
            stock_entry_detail.description,
            stock_entry_detail.stock_uom,
            stock_entry_detail.expense_account,
            stock_entry_detail.cost_center,
            stock_entry_detail.serial_and_batch_bundle,
            stock_entry_detail.batch_no,
            stock_entry_detail.serial_no,
            stock_entry.custom_perintah_produksi.as_("perintah_produksi"),
            stock_entry.purpose,
            stock_entry.name,
        )
        .where(
            (stock_entry.name == stock_entry_detail.parent)
            & (stock_entry.work_order == work_order)
            & (stock_entry.docstatus == 1)
            & (stock_entry_detail.s_warehouse.isnotnull())
            & (
                (
                    stock_entry.purpose.isin(
                        [
                            "Manufacture",
                            "Material Consumption for Manufacture",
                            "Material Transfer for Manufacture",
                        ]
                    ) 
                )
            )
        )
        .orderby(stock_entry.creation, stock_entry_detail.item_code, stock_entry_detail.idx)
    ).run(as_dict=1)

    if not data:
        return []

    voucher_nos = [row.get("name") for row in data if row.get("name")]
    if voucher_nos:
        bundle_data = get_voucher_wise_serial_batch_from_bundle(voucher_no=voucher_nos)
        for row in data:
            key = (row.item_code, row.warehouse, row.name)
            if row.purpose != "Material Transfer for Manufacture":
                key = (row.item_code, row.s_warehouse, row.name)

            if bundle_data.get(key):
                row.update(bundle_data.get(key))

    data.extend(get_stock_entry_loss_item(work_order))

    return data

def get_stock_entry_loss_item(work_order):
	stock_entry = frappe.qb.DocType("Stock Entry")
	stock_entry_detail = frappe.qb.DocType("Stock Entry Detail Loss")

	data = (
		frappe.qb.from_(stock_entry)
		.from_(stock_entry_detail)
		.select(
			stock_entry_detail.item_name,
			stock_entry_detail.original_item,
			stock_entry_detail.item_code,
			stock_entry_detail.qty,
			(stock_entry_detail.s_warehouse).as_("s_warehouse"),
			stock_entry_detail.description,
			stock_entry_detail.stock_uom,
			stock_entry_detail.expense_account,
			stock_entry_detail.cost_center,
			stock_entry_detail.batch_no,
			stock_entry_detail.serial_no,
			stock_entry_detail.perintah_produksi,
			stock_entry.purpose,
            stock_entry.name,
		)
		.where(
			(stock_entry.name == stock_entry_detail.parent)
			& (stock_entry.work_order == work_order)
			& (stock_entry.docstatus == 1)
			& (stock_entry_detail.s_warehouse.isnotnull())
			& (
				(
					stock_entry.purpose.isin(
						[
							"Manufacture"
						]
					) 
				)
			)
		)
		.orderby(stock_entry.creation, stock_entry_detail.item_code, stock_entry_detail.idx)
	).run(as_dict=1)

	if not data:
		return []

	return data