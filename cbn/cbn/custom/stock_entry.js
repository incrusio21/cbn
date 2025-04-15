// Copyright (c) 2024, DAS and Contributors 
// // License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Stock Entry", {
	setup: function (frm) {
        frm.set_query("batch_no", "items", function (doc, cdt, cdn) {
			let item = locals[cdt][cdn];
			let filters = {};

			if (!item.item_code) {
				frappe.throw(__("Please enter Item Code to get Batch Number"));
			} else {
				if (
					in_list(
						[
							"Material Transfer for Manufacture",
							"Manufacture",
							"Repack",
							"Send to Subcontractor",
						],
						doc.purpose
					)
				) {
					filters = {
						item_code: item.item_code,
						posting_date: frm.doc.posting_date || frappe.datetime.nowdate(),
					};
				} else {
					filters = {
						item_code: item.item_code,
					};
				}

				// User could want to select a manually created empty batch (no warehouse)
				// or a pre-existing batch
				if (frm.doc.purpose != "Material Receipt") {
					filters["warehouse"] = item.s_warehouse || item.t_warehouse;
				}

				if (!item.s_warehouse && item.t_warehouse) {
					filters["is_inward"] = 1;
				}

				if (["Material Receipt", "Material Transfer", "Material Issue"].includes(doc.purpose)) {
					filters["include_expired_batches"] = 1;
				}
                
                query = "erpnext.controllers.queries.get_batch_no"
                if(["Material Transfer for Manufacture"].includes(doc.purpose)){
                    query = "cbn.controllers.queries.get_batch_no"
                    filters["detail_name"] = item.name
                }

				return {
					query: query,
					filters: filters,
				};
			}
		});
    },
	refresh: function (frm) {
		if (frm.doc.docstatus === 1) {
			if (
				frm.doc.loss_items &&
				frm.doc.purpose == "Manufacture" &&
				frm.doc.per_transferred_loss < 100
			) {
				frm.add_custom_button(__("Transfer Loss Item"), function () {
					frappe.model.open_mapped_doc({
						method: "erpnext.stock.doctype.stock_entry.stock_entry.make_stock_in_entry",
						frm: frm,
					});
				});
			}
		}
	}
})

cur_frm.cscript.work_order = () => {
	var me = this;
	this.toggle_enable_bom();
	if (!me.frm.doc.work_order || me.frm.doc.job_card) {
		return;
	}

	if(in_list(["Return of Remaining Goods", "Manufacture Conversion", "BK Pengganti Reject", "BK Reject", "BK Sisa"], me.frm.doc.stock_entry_type)){
		return
	}
	
	return frappe.call({
		method: "erpnext.stock.doctype.stock_entry.stock_entry.get_work_order_details",
		args: {
			work_order: me.frm.doc.work_order,
			company: me.frm.doc.company,
		},
		callback: function (r) {
			if (!r.exc) {
				$.each(
					["from_bom", "bom_no", "fg_completed_qty", "use_multi_level_bom"],
					function (i, field) {
						me.frm.set_value(field, r.message[field]);
					}
				);

				if (me.frm.doc.purpose == "Material Transfer for Manufacture" && !me.frm.doc.to_warehouse)
					me.frm.set_value("to_warehouse", r.message["wip_warehouse"]);

				if (
					me.frm.doc.purpose == "Manufacture" ||
					me.frm.doc.purpose == "Material Consumption for Manufacture"
				) {
					if (me.frm.doc.purpose == "Manufacture") {
						if (!me.frm.doc.to_warehouse)
							me.frm.set_value("to_warehouse", r.message["fg_warehouse"]);
					}
					if (!me.frm.doc.from_warehouse)
						me.frm.set_value("from_warehouse", r.message["wip_warehouse"]);
				}
				me.get_items();
			}
		},
	});
}