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
					disabled: 0,
                    status: "Empty"
				},
			};
		});

		if(frm.doc.docstatus == 1 
			&& !frm.doc.use_multi_level_bom 
			&& frm.doc.custom_batch 
			&& !frm.doc.custom_is_sub_assembly 
			&& flt(frm.doc.custom_per_work_order) < 100
		) {
			frm.add_custom_button(
				__("Work Order for Sub Assembly"),
				function () {
					frappe.call({
						method: "cbn.cbn.custom.work_order.create_work_order",
						freeze: true,
						args: {
							work_order: frm.doc.name,
						},
						callback: function (data) {
							if(data.message){
								var message = "<br>" + data.message.join("<br>")
								frappe.msgprint(
									__(
										"List Created Sub Assemblies Work Order " + message
									)
								);
								frm.refresh()
							}
						},
					});
				},
				__("Create")
			);
		}
	},
});