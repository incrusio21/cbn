# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from erpnext.manufacturing.doctype.work_order.work_order import WorkOrder

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
                            "custom_bom": item.bom_no
                        },
                    )

                    if not self.project:
                        self.project = item.get("project")

            self.set_available_qty()

