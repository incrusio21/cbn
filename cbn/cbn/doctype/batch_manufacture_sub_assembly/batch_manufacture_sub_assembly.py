# Copyright (c) 2024, DAS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class BatchManufactureSubAssembly(Document):
	pass

def on_doctype_update():
	frappe.db.add_unique("Batch Manufacture Sub Assembly", ["item_code", "parent"], constraint_name="unique_item_parent")