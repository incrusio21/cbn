// Copyright (c) 2024, DAS and contributors
// For license information, please see license.txt

frappe.ui.form.off("Job Card", "refresh")
frappe.ui.form.on("Job Card", {
    refresh: function (frm) {
		frappe.flags.pause_job = 0;
		frappe.flags.resume_job = 0;
		let has_items = frm.doc.items && frm.doc.items.length;

		if (!frm.is_new() && frm.doc.__onload.work_order_closed) {
			frm.disable_save();
			return;
		}

		let has_stock_entry = frm.doc.__onload && frm.doc.__onload.has_stock_entry ? true : false;

		frm.toggle_enable("for_quantity", !has_stock_entry);

		if (!frm.is_new() && has_items && frm.doc.docstatus < 2) {
			let to_request = frm.doc.for_quantity > frm.doc.transferred_qty;
			let excess_transfer_allowed = frm.doc.__onload.job_card_excess_transfer;

			if (to_request || excess_transfer_allowed) {
				frm.add_custom_button(__("Material Request"), () => {
					frm.trigger("make_material_request");
				});
			}

			// check if any row has untransferred materials
			// in case of multiple items in JC
			let to_transfer = frm.doc.items.some((row) => row.transferred_qty < row.required_qty);

			if (to_transfer || excess_transfer_allowed) {
				frm.add_custom_button(__("Material Transfer"), () => {
					frm.trigger("make_stock_entry");
				}).addClass("btn-primary");
			}
		}

		if (frm.doc.docstatus == 1 && !frm.doc.is_corrective_job_card) {
			frm.trigger("setup_corrective_job_card");
		}

		frm.set_query("quality_inspection", function () {
			return {
				query: "erpnext.stock.doctype.quality_inspection.quality_inspection.quality_inspection_query",
				filters: {
					item_code: frm.doc.production_item,
					reference_name: frm.doc.name,
				},
			};
		});

		frm.trigger("toggle_operation_number");

		// if (
		// 	frm.doc.docstatus == 0 &&
		// 	!frm.is_new() &&
		// 	(frm.doc.for_quantity > frm.doc.total_completed_qty || !frm.doc.for_quantity) &&
		// 	(frm.doc.items || !frm.doc.items.length || frm.doc.for_quantity == frm.doc.transferred_qty)
		// ) {
		// 	// if Job Card is link to Work Order, the job card must not be able to start if Work Order not "Started"
		// 	// and if stock mvt for WIP is required
		// 	if (frm.doc.work_order) {
		// 		frappe.db.get_value(
		// 			"Work Order",
		// 			frm.doc.work_order,
		// 			["skip_transfer", "status"],
		// 			(result) => {
		// 				if (
		// 					result.skip_transfer === 1 ||
		// 					result.status == "In Process" ||
		// 					frm.doc.transferred_qty > 0 ||
		// 					!frm.doc.items.length
		// 				) {
		// 					frm.trigger("prepare_timer_buttons");
		// 				}
		// 			}
		// 		);
		// 	} else {
		// 		frm.trigger("prepare_timer_buttons");
		// 	}
		// }

		frm.trigger("setup_quality_inspection");

		if (frm.doc.work_order) {
			frappe.db.get_value("Work Order", frm.doc.work_order, "transfer_material_against").then((r) => {
				if (r.message.transfer_material_against == "Work Order") {
					frm.set_df_property("items", "hidden", 1);
				}
			});
		}

		let sbb_field = frm.get_docfield("serial_and_batch_bundle");
		if (sbb_field) {
			sbb_field.get_route_options_for_new_doc = () => {
				return {
					item_code: frm.doc.production_item,
					warehouse: frm.doc.wip_warehouse,
					voucher_type: frm.doc.doctype,
				};
			};
		}
	}
})

frappe.ui.form.on("Job Card Time Log'", {
	time_logs_add(frm, cdt, cdn){
		var item = locals[cdt][cdn]

		if(frm.doc.expected_start_date){
			item.from_time = frm.doc.expected_start_date
		}

		if(frm.doc.expected_end_date){
			item.to_time = frm.doc.to_time
		}

		refresh_field("time_logs");
	}
});