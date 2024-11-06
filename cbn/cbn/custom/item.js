// Copyright (c) 2024, DAS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item", {
    refresh(frm) {
		var doc = frm.doc;

        frm.set_query("custom_item_parent", function (doc) {
			return {
				filters: {
                    name: ["!=",doc.production_item],
					disabled: 0,
					custom_is_item_conversion: 0,
				},
			};
		});
    }
})