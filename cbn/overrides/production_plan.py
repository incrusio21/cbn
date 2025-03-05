# Copyright (c) 2025, DAS and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import flt

from erpnext.manufacturing.doctype.production_plan.production_plan import ProductionPlan

class ProductionPlan(ProductionPlan):

    def get_production_items(self):
        item_dict = {}

        for d in self.po_items:
            item_details = {
                "production_item": d.item_code,
                "use_multi_level_bom": d.include_exploded_items if not self.is_batch_manufacture else 0,
                "sales_order": d.sales_order,
                "sales_order_item": d.sales_order_item,
                "material_request": d.material_request,
                "material_request_item": d.material_request_item,
                "bom_no": d.bom_no,
                "description": d.description,
                "stock_uom": d.stock_uom,
                "company": self.company,
                "fg_warehouse": d.warehouse,
                "production_plan": self.name,
                "production_plan_item": d.name,
                "product_bundle_item": d.product_bundle_item,
                "planned_start_date": d.planned_start_date,
                "project": self.project,
                "custom_batch": self.batch_manufacture if self.is_batch_manufacture else "",
                "allow_alternative_item": 1
            }

            key = (d.item_code, d.sales_order, d.sales_order_item, d.warehouse)
            if self.combine_items:
                key = (d.item_code, d.sales_order, d.warehouse)

            if not d.sales_order:
                key = (d.name, d.item_code, d.warehouse)

            if not item_details["project"] and d.sales_order:
                item_details["project"] = frappe.get_cached_value("Sales Order", d.sales_order, "project")

            if self.get_items_from == "Material Request":
                item_details.update({"qty": d.planned_qty})
                item_dict[(d.item_code, d.material_request_item, d.warehouse)] = item_details
            else:
                item_details.update(
                    {
                        "qty": flt(item_dict.get(key, {}).get("qty"))
                        + (flt(d.planned_qty) - flt(d.ordered_qty))
                    }
                )
                item_dict[key] = item_details

        return item_dict
    
    def prepare_data_for_sub_assembly_items(self, row, wo_data):
        for field in [
            "production_item",
            "item_name",
            "qty",
            "fg_warehouse",
            "description",
            "bom_no",
            "stock_uom",
            "bom_level",
            "schedule_date",
        ]:
            if row.get(field):
                wo_data[field] = row.get(field)

        wo_data.update(
            {
                "use_multi_level_bom": 0,
                "production_plan": self.name,
                "production_plan_sub_assembly_item": row.name,
                "allow_alternative_item": 1,
                "custom_batch": self.batch_manufacture if self.is_batch_manufacture else ""
            }
        )