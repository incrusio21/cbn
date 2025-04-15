# Copyright (c) 2024, DAS and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from frappe.utils import flt

@frappe.whitelist()
def make_quality_inspections(doctype, docname, items):
    if isinstance(items, str):
        items = json.loads(items)

    batch_manufacture = None
    if doctype in ["Stock Entry"]:
        batch_manufacture = frappe.get_value(doctype, docname, ["custom_batch"])

    inspections = []
    doc_type = doctype + (" Item" if doctype not in ["Stock Entry"] else " Detail")
    for item in items:
        if flt(item.get("sample_size")) > flt(item.get("qty")):
            frappe.throw(
                _(
                    "{item_name}'s Sample Size ({sample_size}) cannot be greater than the Accepted Quantity ({accepted_quantity})"
                ).format(
                    item_name=item.get("item_name"),
                    sample_size=item.get("sample_size"),
                    accepted_quantity=item.get("qty"),
                )
            )
        
        if not frappe.db.exists(doc_type, item.get("docname")):
            frappe.throw(
                _(
                    "Please save the document first before proceeding."
                )
            )

        quality_inspection = frappe.get_doc(
            {
                "doctype": "Quality Inspection",
                "inspection_type": "Incoming",
                "inspected_by": frappe.session.user,
                "reference_type": doctype,
                "reference_name": docname,
                "custom_reference_no": item.get("docname"),
                "custom_batch": batch_manufacture,
                "item_code": item.get("item_code"),
                "description": item.get("description"),
                "sample_size": flt(item.get("sample_size")),
                "item_serial_no": item.get("serial_no").split("\n")[0] if item.get("serial_no") else None,
                "batch_no": item.get("batch_no"),
            }
        ).insert()

        quality_inspection.save()
        inspections.append(quality_inspection.name)
        if item.get("docname"):
            frappe.db.set_value(doc_type, item.get("docname"), "quality_inspection", quality_inspection.name)

    return inspections

