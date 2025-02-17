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
                    filters["parent"] = item.parent
                }

				return {
					query: query,
					filters: filters,
				};
			}
		});
    }
})