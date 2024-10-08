// Copyright (c) 2024, DAS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Work Order", {
	refresh(frm) {
        frm.set_query("custom_batch", function (doc) {
            if(!doc.production_item){
                frappe.throw("Select Production Item First")
            }

			return {
				filters: {
                    item_code: doc.production_item,
                    status: "Empty"
				},
			};
		});
	},
});