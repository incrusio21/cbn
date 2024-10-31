// Copyright (c) 2024, DAS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Work Order", {
	refresh(frm) {
        frm.set_query("custom_batch", function (doc) {
            if(!doc.production_item){
                frappe.throw("Select Production Item First")
            }

			if(!doc.custom_date){
                frappe.throw("Select Date First")
            }

			return {
				query: "cbn.controllers.queries.batch_manufacture_query",
				filters: {
                    item_code: doc.production_item,
					disabled: 0,
                    status: "Empty",
					date: doc.custom_date,
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

erpnext.work_order.show_prompt_for_perintah_produksi = function (frm, purpose) {
	let perintah_kerja = [...new Set((frm.doc.required_items || [])
		.filter(item => item.required_qty > item.transferred_qty)
		.map(item => item.custom_perintah_produksi))]

	return new Promise((resolve) => {
		frappe.prompt(
			{
				fieldtype: "Select",
				label: __("Perintah Kerja"),
				fieldname: "perintah_kerja",
				reqd: 1,
				options: perintah_kerja
			},
			(data) => {
				resolve(
					frappe.xcall("erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry", {
						work_order_id: frm.doc.name,
						purpose: purpose,
						perintah_kerja: data.perintah_kerja,
					})
				)
			},
			__("Select Perintah Kerja"),
			__("Create")
		);
	});
}

erpnext.work_order.make_se = function (frm, purpose) {
	if(purpose == "Material Transfer for Manufacture"){
		var prompt = this.show_prompt_for_perintah_produksi(frm, purpose)
	}else{
		var prompt = this.show_prompt_for_qty_input(frm, purpose)
		.then((data) => {
			return frappe.xcall("erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry", {
				work_order_id: frm.doc.name,
				purpose: purpose,
				qty: data.qty,
			});
		})
	}
	
	prompt.then((stock_entry) => {
		frappe.model.sync(stock_entry);
		frappe.set_route("Form", stock_entry.doctype, stock_entry.name);
	});
}