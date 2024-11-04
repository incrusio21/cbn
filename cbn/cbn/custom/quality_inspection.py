# Copyright (c) 2024, DAS and Contributors
# License: GNU General Public License v3. See license.txt

import frappe

def set_job_card_bm(self, method=None):
    if self.reference_type != "Job Card":
        return
    
    self.custom_batch = frappe.get_value(self.reference_type, self.reference_name, "custom_batch")