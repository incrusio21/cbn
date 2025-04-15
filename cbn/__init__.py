__version__ = "0.0.1"


import frappe
from frappe import _
from frappe.model.meta import get_field_precision
from frappe.utils import (
	flt
)


import erpnext

from erpnext.accounts.utils import get_fiscal_year
from erpnext.controllers.stock_controller import QualityInspectionNotSubmittedError, QualityInspectionRequiredError, StockController
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
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
from erpnext.controllers import sales_and_purchase_return
from erpnext.manufacturing.doctype.job_card.job_card import JobCard, OverlapError

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

def custom_get_overlap_for(self, args, open_job_cards=None):
	time_logs = []

	time_logs.extend(self.get_time_logs(args, "Job Card Time Log"))

	time_logs.extend(self.get_time_logs(args, "Job Card Scheduled Time", open_job_cards=open_job_cards))

	if not time_logs:
		return {}

	time_logs = sorted(time_logs, key=lambda x: x.get("to_time"))

	production_capacity = 1
	if self.workstation:
		production_capacity = (
			frappe.get_cached_value("Workstation", self.workstation, "production_capacity") or 1
		)

	# if args.get("employee"):
	# 	# override capacity for employee
	# 	production_capacity = 1

	if not self.has_overlap(production_capacity, time_logs):
		return {}

	if not self.workstation and self.workstation_type and time_logs:
		if workstation_time := self.get_workstation_based_on_available_slot(time_logs):
			self.workstation = workstation_time.get("workstation")
			return workstation_time

	return time_logs[0]

def validate_quantity(doc, args, ref, valid_items, already_returned_items):
	fields = ["stock_qty"]
	if doc.doctype in ["Purchase Receipt", "Purchase Invoice", "Subcontracting Receipt"]:
		if not args.get("return_qty_from_rejected_warehouse"):
			fields.extend(["received_qty", "rejected_qty"])
		else:
			fields = ["received_qty"]

	already_returned_data = already_returned_items.get(args.item_code) or {}

	company_currency = erpnext.get_company_currency(doc.company)
	stock_qty_precision = get_field_precision(
		frappe.get_meta(doc.doctype + " Item").get_field("stock_qty"), company_currency
	)

	for column in fields:
		returned_qty = flt(already_returned_data.get(column, 0)) if len(already_returned_data) > 0 else 0

		if column == "stock_qty" and not args.get("return_qty_from_rejected_warehouse"):
			reference_qty = ref.get(column)
			current_stock_qty = args.get(column)
		elif args.get("return_qty_from_rejected_warehouse"):
			reference_qty = ref.get("rejected_qty") * ref.get("conversion_factor", 1.0)
			current_stock_qty = args.get(column) * args.get("conversion_factor", 1.0)
		else:
			reference_qty = ref.get(column) * ref.get("conversion_factor", 1.0)
			current_stock_qty = args.get(column) * args.get("conversion_factor", 1.0)

		
		max_returnable_qty = flt(reference_qty, stock_qty_precision) - returned_qty
		label = column.replace("_", " ").title()

		
		if reference_qty:
			if flt(args.get(column)) > 0:
				frappe.throw(_("{0} must be negative in return document").format(label))
			elif returned_qty >= reference_qty and args.get(column):
				frappe.throw(
					_("Item {0} has already been returned").format(args.item_code), sales_and_purchase_return.StockOverReturnError
				)
			elif abs(flt(current_stock_qty, stock_qty_precision)) > max_returnable_qty:
				frappe.throw(
					_("Row # {0}: Cannot return more than {1} for Item {2}").format(
						args.idx, max_returnable_qty, args.item_code
					),
					sales_and_purchase_return.StockOverReturnError,
				)
				
StockController.get_sl_entries = get_sl_entries
StockController.update_bundle_details = update_bundle_details
JobCard.get_overlap_for = custom_get_overlap_for
stock_ledger.validate_negative_qty_in_future_sle = validate_negative_qty_in_future_sle
sales_and_purchase_return.validate_quantity = validate_quantity