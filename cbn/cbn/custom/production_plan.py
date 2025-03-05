# Copyright (c) 2025, DAS and Contributors
# License: GNU General Public License v3. See license.txt

import frappe

def update_batch_manufacture(self, method=None):
    if not self.is_batch_manufacture:
        return

    frappe.set_value("Batch Manufacture", self.batch_manufacture, "status", "Used" if self.docstatus == 1 else "Empty")


def add_conversion_batch_manufacture(self, method=None):
    if not self.is_batch_manufacture:
        return

    for item in self.get("po_items"):
        item_parent = frappe.get_cached_value("Item", item.item_code, "custom_item_parent")
        if item_parent != self.item_master:
            frappe.throw("Item {} does not belong to item {}". format(item.code, self.batch_manufacture))

        add_conversion = "add_conversion"
        try:
            frappe.db.savepoint(add_conversion)
            batch_manufacture = frappe.get_doc("Batch Manufacture", self.batch_manufacture)
            batch_manufacture.append("item_conversion", {
                "item_code": item.item_code
            })
            batch_manufacture.flags.ignore_permissions = 1
            batch_manufacture.save()
        except frappe.UniqueValidationError:
            frappe.message_log.pop()
            frappe.db.rollback(save_point=add_conversion)