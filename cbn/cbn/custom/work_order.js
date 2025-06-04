// Copyright (c) 2024, DAS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Work Order", {
	refresh(frm) {
		var doc = frm.doc;
		frm.remove_custom_button(__("Alternate Item"))
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
                    status: "Empty",
					date: doc.custom_date,
				},
			};
		});

		if(doc.docstatus == 1 
			&& !doc.use_multi_level_bom 
			&& doc.custom_batch 
			&& !doc.custom_is_sub_assembly 
			&& flt(doc.custom_per_work_order) < 100
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

		if(
			doc.docstatus == 1 &&
			flt(doc.produced_qty + doc.process_loss_qty) >= flt(doc.qty)
		) {
			frm.add_custom_button(
				__("Bahan Baku Sisa"),
				function () {
					frappe.call({
						method: "cbn.cbn.custom.work_order.create_ste_item_return",
						freeze: true,
						args: {
							work_order_id: doc.name,
						},
						callback: function (r) {
							if(!r.message) return
							var stock_entry = r.message

							frappe.model.sync(stock_entry);
							frappe.set_route("Form", stock_entry.doctype, stock_entry.name);
						},
					});
				},
				__("Create")
			);
		}
		

		if(
			doc.docstatus == 1 &&
			flt(doc.produced_qty - doc.process_loss_qty) >= flt(doc.custom_converted_qty)
		) {
			frm.add_custom_button(
				__("Conversion Uom Manufacture"),
				function () {
					frappe.call({
						method: "cbn.cbn.custom.work_order.create_manufacture_conversion_uom",
						freeze: true,
						args: {
							work_order_id: doc.name,
						},
						callback: function (r) {
							if(!r.message) return
							var stock_entry = r.message

							frappe.model.sync(stock_entry);
							frappe.set_route("Form", stock_entry.doctype, stock_entry.name);
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

erpnext.work_order.get_max_transferable_qty = function (frm, purpose) {
	let max = 0;
	if (purpose === "Disassemble") {
		return flt(frm.doc.produced_qty);
	}

	if (frm.doc.skip_transfer) {
		max = flt(frm.doc.qty) - flt(frm.doc.produced_qty);
	} else {
		if (purpose === "Manufacture") {
			max = flt(frm.doc.material_transferred_for_manufacturing) - flt(frm.doc.produced_qty) - flt(frm.doc.process_loss_qty);
		} else {
			max = flt(frm.doc.qty) - flt(frm.doc.material_transferred_for_manufacturing);
		}
	}
	return flt(max, precision("qty"));
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