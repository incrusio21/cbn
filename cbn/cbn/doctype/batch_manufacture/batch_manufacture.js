// Copyright (c) 2024, DAS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Batch Manufacture", {
	refresh(frm) {
        frm.set_query("item_code", function (doc) {
			return {
                query: "cbn.controllers.queries.item_query",
                filters: { is_production: 1 },
			};
		});
	},
});
