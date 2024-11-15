// Copyright (c) 2024, DAS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Quality Inspection", {
    refresh(frm){
        frm.trigger("update_field")
    },
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
                        frm.set_value("custom_operation", data.operation);
                        frm.set_value("custom_batch_size", data.qty);
                        frm.set_value("custom_line_produksi", data.custom_line_produksi);
                        frm.set_value("custom_start_time", data.actual_start_date);
                        frm.set_value("custom_end_time", data.actual_end_date);
                    }
                }
            })
        }else{
            frm.set_value("custom_operation", "");
        }
    },
    custom_operation(frm){
        frm.trigger("update_field")
    },
    update_field(frm){
        if(!frm.doc.custom_operation) return

        var field_label_map = {};
        $.each(["custom_start_time", "custom_end_time"], function (i, fname) {
			var docfield = frappe.meta.docfield_map["Quality Inspection"][fname];
			if (docfield) {
				var label = __(docfield.label || "", null, docfield.parent).replace(
					/\bTime\b/g,
					""
				); // eslint-disable-line

                field_label_map[fname] = label + frm.doc.custom_operation;
			}
		});

		$.each(field_label_map, function (fname, label) {
			frm.fields_dict[fname].set_label(label);
		});
    }    
})