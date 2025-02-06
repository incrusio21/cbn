# Copyright (c) 2025, DAS and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.model.document import Document

class PerintahProduksi(Document):
	def validate(self):
		self.validate_formula()
	
	def validate_formula(self):
		if not self.formula:
			return
		
		if not re.fullmatch(r"[0-9+\-*/().\s]+", self.formula):
			frappe.throw("The formula contains invalid characters.")

		try:
			eval(self.formula, {"__builtins__": None}, {})
		except Exception:
			frappe.throw("The formula is not a valid mathematical expression.")