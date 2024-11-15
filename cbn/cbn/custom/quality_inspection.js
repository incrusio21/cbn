// Copyright (c) 2024, DAS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Quality Inspection", {
    reference_name(frm){
        if(frm.doc.reference_type == "Job Card" && frm.doc.reference_name){
            frappe.call({
                method: "cbn.cbn.custom.quality_inspection.get_job_card",
                args: {
                    job_card: frm.doc.reference_name
                },
                callback: (r) => {
                    let data = r.message
                    if (data) {
                        frm.set_value("custom_batch_size", data.qty);
                        frm.set_value("custom_line_produksi", data.custom_line_produksi);
                        frm.set_value("custom_start_filling", data.actual_start_date);
                        frm.set_value("custom_end_filling", data.actual_end_date);
                        frm.set_value("custom_start_packing", data.actual_start_date);
                        frm.set_value("custom_end_filling", data.actual_end_date);
                    }
                }
            })
        }
    }
})