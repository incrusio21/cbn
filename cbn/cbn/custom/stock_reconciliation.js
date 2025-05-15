frappe.ui.form.on("Stock Reconciliation", {
    refresh(frm){

        frm.set_query("custom_batch", "items", (frm, cdt, cdn) => {
            var items = locals[cdt][cdn]
            return {
                query: "cbn.controllers.queries.get_filtered_batch_manufacture",
                filters: {
                    item_code: items.item_code,
                }
            };
        })
        
    },
})