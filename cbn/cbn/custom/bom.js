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

frappe.ui.form.on("BOM Item", {
	items_add: function (frm) {
		calculateTotalQty(frm)
	},
	qty: function (frm) {
		calculateTotalQty(frm)
	},
	items_remove: function (frm) {
		calculateTotalQty(frm)
	},
})

function calculateTotalQty(frm) {
	const items = frm.doc.items;
	let total_qty = 0
	items.forEach(el => {
		if (el.qty && !isNaN(el.qty)) {
			total_qty += el.qty
		}
	});
	console.log(total_qty);

	if (total_qty > 0) {
		frm.set_value("custom_total_qty", total_qty)
		frm.refresh_field("custom_total_qty")
	}
}