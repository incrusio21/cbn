// Copyright (c) 2024, DAS and Contributors 
// // License: GNU General Public License v3. See license.txt

frappe.provide("cbn.utils");

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
				if (["Material Transfer for Manufacture"].includes(doc.purpose)) {
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
				(frm.doc.loss_items.length || []) > 0 &&
				frm.doc.purpose == "Manufacture" &&
				frm.doc.per_transferred_loss < 100
			) {
				frm.add_custom_button(__("Transfer Loss Item"), function () {
					cbn.utils.transfer_loss_item({
						frm: frm,
						child_docname: "loss_items",
					});
				});
			}
		}
	}
})

frappe.ui.form.on("Stock Entry Detail", {
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

cbn.utils.transfer_loss_item = function (opts) {
	const frm = opts.frm;
	const child_meta = frappe.get_meta(`Stock Entry Detail Loss`);
	const get_precision = (fieldname) => child_meta.fields.find((f) => f.fieldname == fieldname).precision;

	this.data = frm.doc[opts.child_docname].filter((item) => item.qty > item.transferred_qty).map((d) => {
		return {
			docname: d.name,
			item_code: d.item_code,
			stock_uom: d.uom,
			qty: d.qty,
			transferred_qty: d.transferred_qty,
			good_qty: 0,
			rejected_qty: 0,
		};
	});

	const fields = [
		{
			fieldtype: "Data",
			fieldname: "docname",
			read_only: 1,
			hidden: 1,
		},
		{
			fieldtype: "Link",
			fieldname: "item_code",
			options: "Item",
			in_list_view: 1,
			read_only: 1,
			disabled: 0,
			label: __("Item Code")
		},
		{
			fieldtype: "Link",
			fieldname: "stock_uom",
			options: "UOM",
			in_list_view: 1,
			columns: 1,
			read_only: 1,
			disabled: 0,
			label: __("UOM")
		},
		{
			fieldtype: "Float",
			fieldname: "qty",
			default: 0,
			columns: 1,
			read_only: 1,
			in_list_view: 1,
			precision: get_precision("qty"),
			label: __("Qty"),
		},
		{
			fieldtype: "Float",
			fieldname: "transferred_qty",
			default: 0,
			read_only: 1,
			in_list_view: 1,
			precision: get_precision("transferred_qty"),
			label: __("Transferred Qty"),
		},
		{
			fieldtype: "Float",
			fieldname: "good_qty",
			default: 0,
			read_only: 0,
			in_list_view: 1,
			label: __("Good Qty"),
		},
		{
			fieldtype: "Float",
			fieldname: "rejected_qty",
			default: 0,
			read_only: 0,
			in_list_view: 1,
			label: __("Rejected Qty"),
		},
	]

	let dialog = new frappe.ui.Dialog({
		title: __("Set Transfered Loss Item"),
		size: "extra-large",
		fields: [
			{
				fieldname: "trans_items",
				fieldtype: "Table",
				label: "Items",
				cannot_add_rows: 1,
				cannot_delete_rows: 1,
				in_place_edit: false,
				reqd: 1,
				data: this.data,
				get_data: () => {
					return this.data;
				},
				fields: fields,
			}
		],
		primary_action: function () {
			const trans_items = this.get_values()["trans_items"].filter((item) => !!(item.good_qty || item.rejected_qty));

			if (trans_items.length == 0) {
				frappe.throw("Please fill in the quantity on one of the rows")
			}

			frappe.model.open_mapped_doc({
				method: "cbn.cbn.custom.stock_entry.make_stock_in_entry_loss_transfer",
				frm: frm,
				args: {
					trans_items: trans_items
				},
				freeze: true,
				freeze_message: __("Creating Stock Entry Transfer ..."),
			});
		},
		primary_action_label: __("Submit"),
	})

	dialog.show();
}

cur_frm.cscript.work_order = () => {
	var me = this;
	this.toggle_enable_bom();
	if (!me.frm.doc.work_order || me.frm.doc.job_card) {
		return;
	}

	if (in_list(["Return of Remaining Goods", "Manufacture Conversion", "BK Pengganti Reject", "BK Reject", "BK Sisa"], me.frm.doc.stock_entry_type)) {
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