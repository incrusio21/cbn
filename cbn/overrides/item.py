# Copyright (c) 2025, DAS and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from erpnext.stock.doctype.item.item import Item

class Item(Item):
    
    def clear_retain_sample(self):
        if not (self.has_batch_no or self.custom_has_batch_manufacture):
            self.retain_sample = False

        if not self.retain_sample:
            self.sample_quantity = 0

    def validate_retain_sample(self):
        if self.retain_sample and not frappe.db.get_single_value(
            "Stock Settings", "sample_retention_warehouse"
        ):
            frappe.throw(_("Please select Sample Retention Warehouse in Stock Settings first"))

        if self.retain_sample and not (self.has_batch_no or self.custom_has_batch_manufacture):
            frappe.throw(
                _(
                    "{0} Retain Sample is based on batch, please check Has Batch No to retain sample of item"
                ).format(self.item_code)
            )