# Copyright (c) 2024, DAS and Contributors
# License: GNU General Public License v3. See license.txt
from collections import defaultdict

import frappe
from frappe import _, bold

from frappe.utils import flt
from cbn.cbn.doctype.batch_manufacture.batch_manufacture import get_auto_batch_manufacture

class BatchNegativeStockError(frappe.ValidationError):
	pass

class BatchManufacture:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

        self.set_item_details()
        self.process_batch_manufacture()
        self.validate_batch_inventory()

        self.post_process()
    
    def process_batch_manufacture(self):
        bm_setting = frappe.get_cached_doc("Batch Manufacture Settings")
        self.item_type = ("Production" if self.item_details.item_group == bm_setting.proc_item_group 
		else "Sub Assembly" if self.item_details.item_group == bm_setting.sa_item_group 
		else frappe.throw("The Item Group {} is neither a production item nor a sub-assembly.".format(self.item_details.item_group)))

    def set_item_details(self):
        fields = [
            "has_batch_no",
            "has_serial_no",
            "item_name",
            "item_group",
            "serial_no_series",
            "create_new_batch",
            "batch_number_series",
        ]

        self.item_details = frappe.get_cached_value("Item", self.sle.item_code, fields, as_dict=1)

    def validate_batch_inventory(self):
        batch_manufacture = self.sle.custom_batch
        self.available_batches = get_auto_batch_manufacture(
            frappe._dict(
                {
                    "item_code": self.sle.item_code,
                    "warehouse": self.sle.warehouse,
                    "batch_no": batch_manufacture,
                    "posting_date": self.sle.posting_date,
                    "posting_time": self.sle.posting_time,
                    "consider_negative_batches": True,
                }
            )
        )

        if not self.available_batches:
            return

        available_batches = get_available_batches_qty(self.available_batches)
        
        if batch_manufacture in available_batches and available_batches[batch_manufacture] < 0:
            if flt(available_batches.get(batch_manufacture)) < 0:
                self.validate_negative_batch(batch_manufacture, available_batches[batch_manufacture])

            self.throw_error_message(
                f"Batch {bold(batch_manufacture)} is not available in the selected warehouse {self.warehouse}"
            )

    def validate_negative_batch(self, batch_no, available_qty):
        if available_qty < 0:
            msg = f"""Batch Manufacture {bold(batch_no)} of an Item {bold(self.item_code)}
                has negative stock
                of quantity {bold(available_qty)} on {self.sle.posting_date} {self.sle.posting_time} in the
                warehouse {self.warehouse}"""

            frappe.throw(_(msg), BatchNegativeStockError)
               
    def post_process(self):
        if not self.sle.custom_batch:
            return
        
        self.update_batch_qty()
          
    def update_batch_qty(self):
        batch_no = self.sle.custom_batch
        batches_qty = defaultdict(float)

        for batch in self.available_batches:
            batches_qty[batch.get("batch_no")] += batch.get("qty")

        condition = {
			"Production": ["Batch Manufacture", batch_no],
			"Sub Assembly": ["Batch Manufacture Sub Assembly", {"parent": batch_no, "item_code": self.sle.item_code}],
		}.get(self.item_type)

        if not condition:
            return
        
        if self.item_type == "Sub Assembly" and not frappe.db.exists(condition[0], condition[1]):
            frappe.throw("Item {} not registered in Batch Manufacture {}".format(self.sle.item_code, batch_no))

        frappe.db.set_value(condition[0], condition[1], "batch_qty", batches_qty.get(batch_no, 0))

    def throw_error_message(self, message, exception=frappe.ValidationError):
        frappe.throw(_(message), exception, title=_("Error"))  

def get_available_batches_qty(available_batches):
	available_batches_qty = defaultdict(float)
	for batch in available_batches:
		available_batches_qty[batch.batch_manufacture] += batch.qty

	return available_batches_qty