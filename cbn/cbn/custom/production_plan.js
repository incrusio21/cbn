// Copyright (c) 2025, DAS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Production Plan", {
	refresh(frm) {
		var doc = frm.doc;

        frm.set_query("batch_manufacture", function (doc) {
            if(!doc.item_master){
                frappe.throw("Select Production Item First")
            }

			if(!doc.posting_date){
                frappe.throw("Select Date First")
            }

			return {
				query: "cbn.controllers.queries.batch_manufacture_query",
				filters: {
                    item_code: doc.item_master,
                    status: "Empty",
					date: doc.posting_date,
				},
			};
		});
    },
	planned_start_date(frm){
		frm.doc.po_items.forEach((value) => {
			value.planned_start_date = frm.doc.planned_start_date
		});
		refresh_field("po_items");
	}
})

frappe.ui.form.on("Production Plan Item", {
	po_items_add(frm, cdt, cdn){
		var item = locals[cdt][cdn]

		if(frm.doc.planned_start_date){
			item.planned_start_date = frm.doc.planned_start_date
		}

		refresh_field("po_items");
	}
});