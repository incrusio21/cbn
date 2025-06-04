# Copyright (c) 2024, DAS and Contributors
# License: GNU General Public License v3. See license.txt
import frappe
from frappe import _, bold
from frappe.utils import cint, flt
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import EmptyStockReconciliationItemsError, StockReconciliation, get_stock_balance_for
from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos
from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
from cbn.cbn.doctype.batch_manufacture.batch_manufacture import get_available_batches

class StockReconciliation(StockReconciliation):
    def validate_inventory_dimension(self):
        dimensions = get_inventory_dimensions()
        for dimension in dimensions:
            if dimension.get("fieldname") == "custom_batch":
                continue
            
            for row in self.items:
                if not row.batch_no and row.current_qty and row.get(dimension.get("fieldname")):
                    frappe.throw(
                        _(
                            "Row #{0}: You cannot use the inventory dimension '{1}' in Stock Reconciliation to modify the quantity or valuation rate. Stock reconciliation with inventory dimensions is intended solely for performing opening entries."
                        ).format(row.idx, bold(dimension.get("doctype")))
                    )
                    
    def remove_items_with_no_change(self):
        """Remove items if qty or rate is not changed"""
        self.difference_amount = 0.0

        def _changed(item):
            if item.current_serial_and_batch_bundle:
                bundle_data = frappe.get_all(
                    "Serial and Batch Bundle",
                    filters={"name": item.current_serial_and_batch_bundle},
                    fields=["total_qty as qty", "avg_rate as rate"],
                )[0]

                bundle_data.qty = abs(bundle_data.qty)
                self.calculate_difference_amount(item, bundle_data)

                return True

            inventory_dimensions_dict = {}
            if not item.batch_no and not item.serial_no:
                for dimension in get_inventory_dimensions():
                    if item.get(dimension.get("fieldname")):
                        inventory_dimensions_dict[dimension.get("fieldname")] = item.get(
                            dimension.get("fieldname")
                        )

            item_dict = get_stock_balance_for(
                item.item_code,
                item.warehouse,
                self.posting_date,
                self.posting_time,
                batch_no=item.batch_no,
                inventory_dimensions_dict=inventory_dimensions_dict,
                row=item,
            )

            if item.custom_batch:
                
                bm_item = frappe.get_value("Batch Manufacture", item.custom_batch, "item_code")
                if bm_item != item.item_code:
                    item_conversion = frappe.get_cached_value(
                        "Item", item.item_code, ["custom_is_item_conversion", "custom_item_parent"], as_dict=1
                    )
                    if not (item_conversion.custom_is_item_conversion and bm_item == item_conversion.custom_item_parent):                
                        frappe.throw("Batch Manufacture {} cannot be used by Item {}".format(item.custom_batch, item.item_code))


                available_batches = get_available_batches(
                    frappe._dict(
                        {
                            "item_code": item.item_code,
                            "warehouse": item.warehouse,
                            "batch_no": item.custom_batch,
                            "posting_date": self.posting_date,
                            "posting_time": self.posting_time,
                            "ignore_voucher_nos": [self.name],
                        }
                    )
                )
                
                item_dict["qty"] = available_batches[0].qty if available_batches else 0
            
            if (
                (item.qty is None or item.qty == item_dict.get("qty"))
                and (item.valuation_rate is None or item.valuation_rate == item_dict.get("rate"))
                and (not item.serial_no or (item.serial_no == item_dict.get("serial_nos")))
            ):
                return False
            else:
                # set default as current rates
                if item.qty is None:
                    item.qty = item_dict.get("qty")

                if item.valuation_rate is None:
                    item.valuation_rate = item_dict.get("rate")

                if item_dict.get("serial_nos"):
                    item.current_serial_no = item_dict.get("serial_nos")
                    if self.purpose == "Stock Reconciliation" and not item.serial_no and item.qty:
                        item.serial_no = item.current_serial_no

                item.current_qty = item_dict.get("qty")
                item.current_valuation_rate = item_dict.get("rate")
                self.calculate_difference_amount(item, item_dict)
                return True

        items = list(filter(lambda d: _changed(d), self.items))

        if not items:
            frappe.throw(
                _("None of the items have any change in quantity or value."),
                EmptyStockReconciliationItemsError,
            )

        elif len(items) != len(self.items):
            self.items = items
            for i, item in enumerate(self.items):
                item.idx = i + 1
            frappe.msgprint(_("Removed items with no change in quantity or value."))
               
    def before_submit(self):
        self.update_or_add_conversion_batch_manufacture()

    def update_or_add_conversion_batch_manufacture(self):
        for item in self.get("items"):
            if not (item.custom_batch and item.custom_is_item_conversion):
                continue

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
    
    def update_stock_ledger(self):
        """find difference between current and expected entries
        and create stock ledger entries based on the difference"""
        from erpnext.stock.stock_ledger import get_previous_sle

        sl_entries = []
        for row in self.items:
            if not row.qty and not row.valuation_rate and not row.current_qty:
                self.make_adjustment_entry(row, sl_entries)
                continue

            item = frappe.get_cached_value(
                "Item", row.item_code, ["has_serial_no", "has_batch_no", "custom_has_batch_manufacture"], as_dict=1
            )

            if item.has_serial_no or item.has_batch_no:
                self.get_sle_for_serialized_items(row, sl_entries)
            elif item.custom_has_batch_manufacture:
                self.get_sle_for_manufacture_items(row, sl_entries)
            else:
                if row.serial_and_batch_bundle:
                    frappe.throw(
                        _(
                            "Row #{0}: Item {1} is not a Serialized/Batched Item. It cannot have a Serial No/Batch No against it."
                        ).format(row.idx, frappe.bold(row.item_code))
                    )

                previous_sle = get_previous_sle(
                    {
                        "item_code": row.item_code,
                        "warehouse": row.warehouse,
                        "posting_date": self.posting_date,
                        "posting_time": self.posting_time,
                    }
                )

                if previous_sle:
                    if row.qty in ("", None):
                        row.qty = previous_sle.get("qty_after_transaction", 0)

                    if row.valuation_rate in ("", None):
                        row.valuation_rate = previous_sle.get("valuation_rate", 0)

                if row.qty and not row.valuation_rate and not row.allow_zero_valuation_rate:
                    frappe.throw(
                        _("Valuation Rate required for Item {0} at row {1}").format(row.item_code, row.idx)
                    )

                if (
                    previous_sle
                    and row.qty == previous_sle.get("qty_after_transaction")
                    and (row.valuation_rate == previous_sle.get("valuation_rate") or row.qty == 0)
                ) or (not previous_sle and not row.qty):
                    continue

                sl_entries.append(self.get_sle_for_items(row))

        if sl_entries:
            allow_negative_stock = cint(frappe.db.get_single_value("Stock Settings", "allow_negative_stock"))
            self.make_sl_entries(sl_entries, allow_negative_stock=allow_negative_stock)

    def get_sle_for_manufacture_items(self, row, sl_entries):
        if not row.custom_batch:
            frappe.throw("Row #{}: Please Select Batch Manufacture for Item {}".format(row.idx, row.item_code))
        
        if row.current_qty:
            args = self.get_sle_for_items(row)
            args.update(
                {
                    "actual_qty": -1 * row.current_qty,
                    "valuation_rate": row.current_valuation_rate
                }
            )

            sl_entries.append(args)

        if row.qty != 0:
            args = self.get_sle_for_items(row)
            args.update(
                {
                    "actual_qty": row.qty,
                    "incoming_rate": row.valuation_rate
                }
            )

            sl_entries.append(args)

    def get_sle_for_items(self, row, serial_nos=None, current_bundle=True):
        """Insert Stock Ledger Entries"""

        if not serial_nos and row.serial_no:
            serial_nos = get_serial_nos(row.serial_no)

        data = frappe._dict(
            {
                "doctype": "Stock Ledger Entry",
                "item_code": row.item_code,
                "warehouse": row.warehouse,
                "posting_date": self.posting_date,
                "posting_time": self.posting_time,
                "voucher_type": self.doctype,
                "voucher_no": self.name,
                "voucher_detail_no": row.name,
                "custom_batch": row.custom_batch,
                "actual_qty": 0,
                "company": self.company,
                "stock_uom": frappe.db.get_value("Item", row.item_code, "stock_uom"),
                "is_cancelled": 1 if self.docstatus == 2 else 0,
                "valuation_rate": flt(row.valuation_rate, row.precision("valuation_rate")),
            }
        )

        if not row.batch_no:
            data.qty_after_transaction = flt(row.qty, row.precision("qty"))

        dimensions = get_inventory_dimensions()
        has_dimensions = False
        for dimension in dimensions:
            if row.get(dimension.get("fieldname")):
                has_dimensions = True

        if self.docstatus == 2 and (not row.batch_no or not row.serial_and_batch_bundle):
            if row.current_qty and current_bundle:
                data.actual_qty = -1 * row.current_qty
                data.qty_after_transaction = flt(row.current_qty)
                data.previous_qty_after_transaction = flt(row.qty)
                data.valuation_rate = flt(row.current_valuation_rate)
                data.serial_and_batch_bundle = row.current_serial_and_batch_bundle
                data.stock_value = data.qty_after_transaction * data.valuation_rate
                data.stock_value_difference = -1 * flt(row.amount_difference)
            else:
                data.actual_qty = row.qty
                data.qty_after_transaction = 0.0
                data.serial_and_batch_bundle = row.serial_and_batch_bundle
                data.valuation_rate = flt(row.valuation_rate)
                data.stock_value_difference = -1 * flt(row.amount_difference)

        elif self.docstatus == 1 and has_dimensions and (not row.batch_no or not row.serial_and_batch_bundle):
            data.actual_qty = row.qty
            data.qty_after_transaction = 0.0
            data.incoming_rate = flt(row.valuation_rate)

        self.update_inventory_dimensions(row, data)

        return data
    
        