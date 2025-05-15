# Copyright (c) 2024, DAS and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import flt

def remove_qa_not_in_items(self, method=None):
    if not self.inspection_required:
        return
    
    qa_list = frappe.db.get_list("Quality Inspection", 
        filters={ "reference_type": self.doctype, "reference_name": self.name }, fields=["name", "custom_reference_no", "docstatus"])
    
    for row in qa_list:
        if not row.custom_reference_no or self.get("items", {"name": row.custom_reference_no}):
            continue
        
        if row.docstatus == 1:
            frappe.throw("Please cancel Document {} first".format(
                frappe.get_desk_link("Quality Inspection", row.name),
            ))
        else:
            frappe.delete_doc("Quality Inspection", row.name)
        

def validate_and_update_loss_item(self, method):
    if self.stock_entry_type not in ["Transfer Process Loss Item"]:
        return

    ste_man = frappe.get_doc("Stock Entry", self.manufacture_stock_entry)
    for d in ste_man.loss_items:
        transferred_qty = frappe.get_all(
            "Stock Entry Detail",
            fields=["sum(qty) as qty"],
            filters={
                "ste_child_loss": d.name,
                "docstatus": 1,
            },
        )[0].qty or 0.0

        if d.qty < transferred_qty:
            frappe.throw("Row {}: quantity to transfer exceeds remaining quantity for Item {}.".format(d.idx, d.item_code))

        d.db_set("transferred_qty", transferred_qty) 

    args = {
        "source_dt": "Stock Entry Detail",
        "target_field": "transferred_qty",
        "target_ref_field": "qty",
        "target_dt": "Stock Entry Detail Loss",
        "join_field": "ste_child_loss",
        "target_parent_dt": "Stock Entry",
        "target_parent_field": "per_transferred_loss",
        "source_field": "qty",
        "percent_join_field_parent": "manufacture_stock_entry",
    }

    self._update_percent_field_in_targets(args, update_modified=True)

@frappe.whitelist()
def make_stock_in_entry_loss_transfer(source_name, target_doc=None):
    
    target = frappe.new_doc("Stock Entry")
    target.stock_entry_type = "Transfer Process Loss Item"
    target.purpose = None
    target.manufacture_stock_entry = source_name
    
    doc = frappe.get_doc("Stock Entry", source_name)
    for f in [
        "work_order", "custom_batch", 
        "custom_batch_size", "custom_gramasi", "custom_kode_produksi", 
        "custom_production_item", "custom_other_comments_or_special_instructions"]:
        if doc.get(f):
            target.set(f, doc.get(f))

    for d in frappe.flags.args.trans_items:
        d = frappe._dict(d)
        if flt(d.good_qty + d.rejected_qty) > flt(d.transferred_qty + d.qty):
            frappe.throw("Row {}: quantity to transfer exceeds remaining quantity for Item {}.".format(d.idx, d.item_code))
            
        std = frappe.get_doc("Stock Entry Detail Loss", d.docname).as_dict(no_default_fields=True)
        std.ste_child_loss = d.docname
        
        t_wh = frappe.get_value("Perintah Produksi Warehouse", {
            "parent": std.perintah_produksi,
            "company": target.company
        }, ["good_warehouse", "rejected_warehouse"], as_dict=1)

        if d.good_qty:
            target.append("items", {
                **std,
                "qty": d.good_qty,
                "t_warehouse": t_wh.good_warehouse,
            })
        
        if d.rejected_qty:
            target.append("items", {
                **std,
                "qty": d.rejected_qty,
                "t_warehouse": t_wh.rejected_warehouse,
            })
    
    target.set_purpose_for_stock_entry()

    return target

# Custom Krisna 06052025
def calculate_total_qty(self, method):
    if not self.items:
        return
    
    self.custom_total_qty = 0
    for item in self.items:
        self.custom_total_qty += item.qty
        