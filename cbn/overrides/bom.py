# Copyright (c) 2025, DAS and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import flt

import erpnext
from erpnext.manufacturing.doctype.bom.bom import BOM

class BOM(BOM):
    def get_exploded_items(self):
        """Get all raw materials including items from child bom"""
        self.cur_exploded_items = {}
        for d in self.get("items"):
            if d.bom_no:
                self.get_child_exploded_items(d.bom_no, d.stock_qty)
            elif d.item_code:
                self.add_to_cur_exploded_items(
                    frappe._dict(
                        {
                            "item_code": d.item_code,
                            "item_name": d.item_name,
                            "operation": d.operation,
                            "source_warehouse": d.source_warehouse,
                            "description": d.description,
                            "perintah_produksi": d.get("perintah_produksi"),
                            "image": d.image,
                            "stock_uom": d.stock_uom,
                            "stock_qty": flt(d.stock_qty),
                            "rate": flt(d.base_rate) / (flt(d.conversion_factor) or 1.0),
                            "include_item_in_manufacturing": d.include_item_in_manufacturing,
                            "sourced_by_supplier": d.sourced_by_supplier,
                        }
                    )
                )

    def company_currency(self):
        return erpnext.get_company_currency(self.company)

    def add_to_cur_exploded_items(self, args):
        key = (args.item_code, args.perintah_produksi) if args.get("perintah_produksi") else args.item_code
        if self.cur_exploded_items.get(key):
            self.cur_exploded_items[key]["stock_qty"] += args.stock_qty
        else:
            self.cur_exploded_items.setdefault(key, args)

    def get_child_exploded_items(self, bom_no, stock_qty):
        """Add all items from Flat BOM of child BOM"""
        # Did not use qty_consumed_per_unit in the query, as it leads to rounding loss
        child_fb_items = frappe.db.sql(
            """
            SELECT
                bom_item.item_code,
                bom_item.item_name,
                bom_item.perintah_produksi,
                bom_item.description,
                bom_item.source_warehouse,
                bom_item.operation,
                bom_item.stock_uom,
                bom_item.stock_qty,
                bom_item.rate,
                bom_item.include_item_in_manufacturing,
                bom_item.sourced_by_supplier,
                bom_item.stock_qty / ifnull(bom.quantity, 1) AS qty_consumed_per_unit
            FROM `tabBOM Explosion Item` bom_item, `tabBOM` bom
            WHERE
                bom_item.parent = bom.name
                AND bom.name = %s
                AND bom.docstatus = 1
        """,
            bom_no,
            as_dict=1,
        )

        for d in child_fb_items:
            self.add_to_cur_exploded_items(
                frappe._dict(
                    {
                        "item_code": d["item_code"],
                        "item_name": d["item_name"],
                        "perintah_produksi": d["perintah_produksi"],
                        "source_warehouse": d["source_warehouse"],
                        "operation": d["operation"],
                        "description": d["description"],
                        "stock_uom": d["stock_uom"],
                        "stock_qty": d["qty_consumed_per_unit"] * stock_qty,
                        "rate": flt(d["rate"]),
                        "include_item_in_manufacturing": d.get("include_item_in_manufacturing", 0),
                        "sourced_by_supplier": d.get("sourced_by_supplier", 0),
                    }
                )
            )