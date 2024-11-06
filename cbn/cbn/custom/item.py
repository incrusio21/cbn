# Copyright (c) 2024, DAS and Contributors
# License: GNU General Public License v3. See license.txt

import frappe

def validate_item_parent(self, method):
    if self.name == self.custom_item_parent:
        frappe.throw("This item cannot be selected as its own parent.")

    # memastikan value tidak bermasalah
    if not self.custom_is_item_conversion:
        self.custom_item_parent = None
    elif not self.custom_item_parent:
        self.custom_is_item_conversion = 0
        
    # skip jika item parent kosong dan data baru
    if not self.custom_item_parent and self.is_new():
        return
    
    # jika sudah memiliki batch manufacture, item tidak boleh menjadi item conversion
    if self.custom_is_item_conversion and frappe.db.exists("Batch Manufacture", {"item_code": self.name }):
        frappe.throw("Item {} already has a Batch Manufacture.".format(self.name))

    previous = self.get_doc_before_save()
    
    # jika nilai now dan last sama skip
    if previous and self.custom_item_parent == previous.custom_item_parent:
        return
    elif previous and previous.custom_item_parent and self.custom_item_parent != previous.custom_item_parent:
        # jika nilai now tidak sama dengan nilai lasts
        if frappe.db.exists("Batch Manufacture Conversion", {"item_code", self.name}):
            frappe.throw("Item already used in Batch Manufacture")
    
    # skip jika item parent kosong
    if not self.custom_item_parent:
        return

    item_parent = frappe.db.get_value("Item", self.custom_item_parent, ["custom_is_item_conversion", "stock_uom"], as_dict=1)
    if item_parent.custom_is_item_conversion:
        frappe.throw("Item {} cant be Item Parent".format(self.custom_item_parent))
    
    if item_parent.stock_uom == self.stock_uom:
        frappe.throw("Item {} has the same UOM".format(self.custom_item_parent))