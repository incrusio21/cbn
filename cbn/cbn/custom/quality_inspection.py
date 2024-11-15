# Copyright (c) 2024, DAS and Contributors
# License: GNU General Public License v3. See license.txt

import frappe

def set_job_card_bm(self, method=None):
    if self.reference_type != "Job Card":
        return
    
    self.custom_batch = frappe.get_value(self.reference_type, self.reference_name, "custom_batch")

@frappe.whitelist()
def get_job_card(job_card):
    jc = frappe.qb.DocType("Job Card")
    wo = frappe.qb.DocType("Work Order")

    query = (
        frappe.qb.from_(jc)
        .inner_join(wo)
        .on(jc.work_order == wo.name)
        .select(
            jc.actual_start_date,
            jc.actual_end_date,
            wo.qty,
            wo.custom_line_produksi,
        )
        .where(jc.name == job_card)
        .limit(1)
    )

    data = query.run(as_dict=True)

    return data[0] if data else {}