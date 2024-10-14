// Copyright (c) 2024, DAS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
        frm.set_query("custom_batch", "items",function (doc, cdt, cdn) {
            var item = locals[cdt][cdn]
            if(!item.item_code){
                frappe.throw("Select Item Code First")
            }

			return {
                query: "cbn.controllers.queries.batch_manufacture_query",
				filters: {
                    item_code: item.item_code,
					item_group: item.item_group,
				},
			};
		});
    }
})