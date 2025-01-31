__version__ = "0.0.1"

import frappe
from frappe import _
from frappe.utils.data import flt

from erpnext.accounts.utils import get_fiscal_year
from erpnext.controllers.stock_controller import StockController
from erpnext.stock import stock_ledger
from erpnext.stock.stock_ledger import (
	NegativeStockError,
	get_future_sle_with_negative_batch_qty,
	get_future_sle_with_negative_qty, 
	is_negative_stock_allowed, is_negative_with_precision,
	validate_reserved_stock
)
from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
	get_type_of_transaction,
)

def get_sl_entries(self, d, args):
    sl_dict = frappe._dict(
        {
            "item_code": d.get("item_code", None),
            "warehouse": d.get("warehouse", None),
            "serial_and_batch_bundle": d.get("serial_and_batch_bundle"),
            "custom_batch": d.get("custom_batch"),
            "posting_date": self.posting_date,
            "posting_time": self.posting_time,
            "fiscal_year": get_fiscal_year(self.posting_date, company=self.company)[0],
            "voucher_type": self.doctype,
            "voucher_no": self.name,
            "voucher_detail_no": d.name,
            "actual_qty": (self.docstatus == 1 and 1 or -1) * flt(d.get("stock_qty")),
            "stock_uom": frappe.get_cached_value(
                "Item", args.get("item_code") or d.get("item_code"), "stock_uom"
            ),
            "incoming_rate": 0,
            "company": self.company,
            "project": d.get("project") or self.get("project"),
            "is_cancelled": 1 if self.docstatus == 2 else 0,
        }
    )

    if d.get("item_row") and d.item_row.get("custom_batch"):
        sl_dict.update({"custom_batch": d.item_row.custom_batch })

    sl_dict.update(args)
    self.update_inventory_dimensions(d, sl_dict)

    if self.docstatus == 2:
        # To handle denormalized serial no records, will br deprecated in v16
        for field in ["serial_no", "batch_no"]:
            if d.get(field):
                sl_dict[field] = d.get(field)

    return sl_dict
def update_bundle_details(self, bundle_details, table_name, row, is_rejected=False):
    from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos

    # Since qty field is different for different doctypes
    qty = row.get("qty")
    warehouse = row.get("warehouse")

    if table_name == "packed_items":
        type_of_transaction = "Inward"
        if not self.is_return:
            type_of_transaction = "Outward"
    elif table_name == "supplied_items":
        qty = row.consumed_qty
        warehouse = self.supplier_warehouse
        type_of_transaction = "Outward"
        if self.is_return:
            type_of_transaction = "Inward"
    else:
        type_of_transaction = get_type_of_transaction(self, row)

    if hasattr(row, "stock_qty"):
        qty = row.stock_qty

    if self.doctype == "Stock Entry":
        qty = row.transfer_qty
        warehouse = row.s_warehouse or row.t_warehouse

    serial_nos = row.serial_no
    if is_rejected:
        serial_nos = row.get("rejected_serial_no")
        type_of_transaction = "Inward" if not self.is_return else "Outward"
        qty = flt(row.get("rejected_qty") * (row.conversion_factor or 1.0))
        warehouse = row.get("rejected_warehouse")

    if (
        self.is_internal_transfer()
        and self.doctype in ["Sales Invoice", "Delivery Note"]
        and self.is_return
    ):
        warehouse = row.get("target_warehouse") or row.get("warehouse")
        type_of_transaction = "Outward"

    bundle_details.update(
        {
            "qty": qty,
            "is_rejected": is_rejected,
            "type_of_transaction": type_of_transaction,
            "warehouse": warehouse,
            "batches": frappe._dict({row.batch_no: qty}) if row.batch_no else None,
            "serial_nos": get_serial_nos(serial_nos) if serial_nos else None,
            "batch_no": row.batch_no,
        }
    )
          
def validate_negative_qty_in_future_sle(args, allow_negative_stock=False):
    if allow_negative_stock or is_negative_stock_allowed(item_code=args.item_code):
        return

    if (
        args.voucher_type == "Stock Reconciliation"
        and args.actual_qty < 0
        and args.get("serial_and_batch_bundle")
        and frappe.db.get_value("Stock Reconciliation Item", args.voucher_detail_no, "qty") > 0
    ):
        return

    if args.actual_qty >= 0 and args.voucher_type != "Stock Reconciliation":
        return

    neg_sle = get_future_sle_with_negative_qty(args)

    if is_negative_with_precision(neg_sle):
        message = _("{0} units of {1} needed in {2} on {3} {4} for {5} to complete this transaction.").format(
            abs(neg_sle[0]["qty_after_transaction"]),
            frappe.get_desk_link("Item", args.item_code),
            frappe.get_desk_link("Warehouse", args.warehouse),
            neg_sle[0]["posting_date"],
            neg_sle[0]["posting_time"],
            frappe.get_desk_link(neg_sle[0]["voucher_type"], neg_sle[0]["voucher_no"]),
        )

        frappe.throw(message, NegativeStockError, title=_("Insufficient Stock"))

    if args.batch_no:
        neg_batch_sle = get_future_sle_with_negative_batch_qty(args)
        if is_negative_with_precision(neg_batch_sle, is_batch=True):
            message = _(
                "{0} units of {1} needed in {2} on {3} {4} for {5} to complete this transaction."
            ).format(
                abs(neg_batch_sle[0]["cumulative_total"]),
                frappe.get_desk_link("Batch", args.batch_no),
                frappe.get_desk_link("Warehouse", args.warehouse),
                neg_batch_sle[0]["posting_date"],
                neg_batch_sle[0]["posting_time"],
                frappe.get_desk_link(neg_batch_sle[0]["voucher_type"], neg_batch_sle[0]["voucher_no"]),
            )
            frappe.throw(message, NegativeStockError, title=_("Insufficient Stock for Batch"))

    if args.custom_batch:
        neg_batch_sle = get_future_sle_with_negative_batch_manufactur_qty(args)
        if is_negative_with_precision(neg_batch_sle, is_batch=True):
            message = _(
                "{0} units of {1} needed in {2} on {3} {4} for {5} to complete this transaction."
            ).format(
                abs(neg_batch_sle[0]["cumulative_total"]),
                frappe.get_desk_link("Batch Manufacture", args.custom_batch),
                frappe.get_desk_link("Warehouse", args.warehouse),
                neg_batch_sle[0]["posting_date"],
                neg_batch_sle[0]["posting_time"],
                frappe.get_desk_link(neg_batch_sle[0]["voucher_type"], neg_batch_sle[0]["voucher_no"]),
            )
            frappe.throw(message, NegativeStockError, title=_("Insufficient Stock for Batch"))
            
    if args.reserved_stock:
        validate_reserved_stock(args)

def get_future_sle_with_negative_batch_manufactur_qty(args):
	return frappe.db.sql(
		"""
		with batch_ledger as (
			select
				posting_date, posting_time, posting_datetime, voucher_type, voucher_no,
				sum(actual_qty) over (order by posting_datetime, creation) as cumulative_total
			from `tabStock Ledger Entry`
			where
				item_code = %(item_code)s
				and warehouse = %(warehouse)s
				and custom_batch=%(custom_batch)s
				and is_cancelled = 0
			order by posting_datetime, creation
		)
		select * from batch_ledger
		where
			cumulative_total < 0.0
			and posting_datetime >= %(posting_datetime)s
		limit 1
	""",
		args,
		as_dict=1,
	)

StockController.get_sl_entries = get_sl_entries
StockController.update_bundle_details = update_bundle_details
stock_ledger.validate_negative_qty_in_future_sle = validate_negative_qty_in_future_sle