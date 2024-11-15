// Copyright (c) 2024, DAS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Quality Inspection", {
    reference_name(frm){
        if(frm.doc.reference_type == "Job Card" && frm.doc.reference_name){
            frappe.db.get_value("Job Card", frm.doc.reference_name, ["name", "actual_start_date", "actual_end_date"], 
                (r) => {
                if (r && r.name) {
                    frm.set_value("custom_start_filling", r.actual_start_date);
                    frm.set_value("custom_end_filling", r.actual_end_date);
                }
            })
        }
    }
})