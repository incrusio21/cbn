// Copyright (c) 2025, DAS and Contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("BOM", {
    setup(frm) {
        frm.set_query("perintah_produksi", "items", function (doc, cdt, cdn) {
			var d = locals[cdt][cdn];
			return {
				query: "cbn.controllers.queries.perintah_produksi_query",
				filters: {
					item: d.item_code,
				},
			};
		});
    }
})