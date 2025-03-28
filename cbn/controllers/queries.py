# Copyright (c) 2024, DAS and Contributors
# License: GNU General Public License v3. See license.txt

import json
from collections import OrderedDict
from pypika import functions as fn

import frappe
from frappe import scrub
from frappe.desk.reportview import get_filters_cond, get_match_cond
from frappe.query_builder.functions import IfNull
from frappe.utils import getdate, nowdate

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def item_query(doctype, txt, searchfield, start, page_len, filters, as_dict=False):
    doctype = "Item"
    conditions = []

    if isinstance(filters, str):
        filters = json.loads(filters)

    # Get searchfields from meta and use in Item Link field query
    meta = frappe.get_meta(doctype, cached=True)
    searchfields = meta.get_search_fields()

    columns = ""
    extra_searchfields = [field for field in searchfields if field not in ["name", "description"]]

    if extra_searchfields:
        columns += ", " + ", ".join(extra_searchfields)

    if "description" in searchfields:
        columns += """, if(length(tabItem.description) > 40, \
            concat(substr(tabItem.description, 1, 40), "..."), description) as description"""

    searchfields = searchfields + [
        field
        for field in [searchfield or "name", "item_code", "item_group", "item_name"]
        if field not in searchfields
    ]
    searchfields = " or ".join([field + " like %(txt)s" for field in searchfields])

    if filters and isinstance(filters, dict):
        if filters.get("customer") or filters.get("supplier"):
            party = filters.get("customer") or filters.get("supplier")
            item_rules_list = frappe.get_all(
                "Party Specific Item",
                filters={"party": party},
                fields=["restrict_based_on", "based_on_value"],
            )

            filters_dict = {}
            for rule in item_rules_list:
                if rule["restrict_based_on"] == "Item":
                    rule["restrict_based_on"] = "name"
                filters_dict[rule.restrict_based_on] = []

            for rule in item_rules_list:
                filters_dict[rule.restrict_based_on].append(rule.based_on_value)

            for filter in filters_dict:
                filters[scrub(filter)] = ["in", filters_dict[filter]]

            if filters.get("customer"):
                del filters["customer"]
            else:
                del filters["supplier"]
        else:
            filters.pop("customer", None)
            filters.pop("supplier", None)
            
        if filters.get("is_production") or filters.get("is_sub_assembly"):
            bm_setting = frappe.get_cached_doc("Batch Manufacture Settings")
            item_group = bm_setting.proc_item_group if filters.get("is_production") else bm_setting.sa_item_group

            filters["item_group"] = item_group

            if filters.get("is_production"):
                del filters["is_production"]
            else:
                del filters["is_sub_assembly"]
        else:
            filters.pop("is_production", None)
            filters.pop("is_sub_assembly", None)

    description_cond = ""
    if frappe.db.count(doctype, cache=True) < 50000:
        # scan description only if items are less than 50000
        description_cond = "or tabItem.description LIKE %(txt)s"

    return frappe.db.sql(
        """select
            tabItem.name {columns}
        from tabItem
        where tabItem.docstatus < 2
            and tabItem.disabled=0
            and tabItem.has_variants=0
            and (tabItem.end_of_life > %(today)s or ifnull(tabItem.end_of_life, '0000-00-00')='0000-00-00')
            and ({scond} or tabItem.item_code IN (select parent from `tabItem Barcode` where barcode LIKE %(txt)s)
                {description_cond})
            {fcond} {mcond}
        order by
            if(locate(%(_txt)s, name), locate(%(_txt)s, name), 99999),
            if(locate(%(_txt)s, item_name), locate(%(_txt)s, item_name), 99999),
            idx desc,
            name, item_name
        limit %(start)s, %(page_len)s """.format(
            columns=columns,
            scond=searchfields,
            fcond=get_filters_cond(doctype, filters, conditions).replace("%", "%%"),
            mcond=get_match_cond(doctype).replace("%", "%%"),
            description_cond=description_cond,
        ),
        {
            "today": nowdate(),
            "txt": "%%%s%%" % txt,
            "_txt": txt.replace("%", ""),
            "start": start,
            "page_len": page_len,
        },
        as_dict=as_dict,
    )

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def batch_manufacture_query(doctype, txt, searchfield, start, page_len, filters, as_dict=False):
    doctype = "Batch Manufacture"
    join = ""
    conditions = []

    if isinstance(filters, str):
        filters = json.loads(filters)

    # Get searchfields from meta and use in Item Link field query
    meta = frappe.get_meta(doctype, cached=True)
    searchfields = meta.get_search_fields()

    columns = ""
    extra_searchfields = [field for field in searchfields if field not in ["name"]]

    if extra_searchfields:
        columns += ", " + ", ".join(extra_searchfields)

    searchfields = searchfields + [
        field
        for field in [searchfield or "name"]
        if field not in searchfields
    ]

    searchfields = " or ".join([f"`tab{doctype}`." + field + " like %(txt)s" for field in searchfields])

    if filters and isinstance(filters, dict):    
        if filters.get("item_group"):
            bm_setting = frappe.get_cached_doc("Batch Manufacture Settings")
            if bm_setting.sa_item_group == filters.get("item_group"):
                doctype = "Batch Manufacture Sub Assembly"
                join += """ join `tabBatch Manufacture Sub Assembly` on `tabBatch Manufacture Sub Assembly`.parent = `tabBatch Manufacture`.name """
            elif bm_setting.proc_item_group != filters.get("item_group"):
                return []
    
            del filters["item_group"]
        else:
            filters.pop("item_group", None)

        if filters.get("date"):
            date = getdate(filters.get("date"))
            filters["bulan"] = date.month
            filters["tahun"] = date.year

            del filters["date"]
        else:
            filters.pop("date", None)

        # if filters.get("item_code") and \
        #     doctype == "Batch Manufacture" and \
        #     frappe.get_cached_value("Item", filters["item_code"], "custom_is_item_conversion"):
        #     doctype = "Batch Manufacture Conversion"
        #     join += """ join `tabBatch Manufacture Conversion` on `tabBatch Manufacture Conversion`.parent = `tabBatch Manufacture`.name """

    # filters["batch_qty"] = [">", 0]

    description_cond = ""
    if frappe.db.count(doctype, cache=True) < 50000:
        # scan description only if items are less than 50000
        description_cond = "or `tabBatch Manufacture`.description LIKE %(txt)s"

    return frappe.db.sql(
        """select
            `tabBatch Manufacture`.name {columns}
        from `tabBatch Manufacture` {join}
        where `tabBatch Manufacture`.docstatus < 2
            and `tabBatch Manufacture`.disabled=0
            and (`tabBatch Manufacture`.expiry_date > %(today)s or ifnull(`tabBatch Manufacture`.expiry_date, '0000-00-00')='0000-00-00')
            and ({scond}
                {description_cond})
            {fcond} {mcond}
        order by
            if(locate(%(_txt)s, `tabBatch Manufacture`.name), locate(%(_txt)s, `tabBatch Manufacture`.name), 99999),
            `tabBatch Manufacture`.idx desc,
            `tabBatch Manufacture`.name
        limit %(start)s, %(page_len)s """.format(
            columns=columns,
            join=join,
            scond=searchfields,
            fcond=get_filters_cond(doctype, filters, conditions).replace("%", "%%"),
            mcond=get_match_cond(doctype).replace("%", "%%"),
            description_cond=description_cond,
        ),
        {
            "today": nowdate(),
            "txt": "%%%s%%" % txt,
            "_txt": txt.replace("%", ""),
            "start": start,
            "page_len": page_len,
        },
        as_dict=as_dict,
        debug=1
    )

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def perintah_produksi_query(doctype, txt, searchfield, start, page_len, filters, as_dict=False):
    doctype = "Perintah Produksi"
    conditions = []

    if isinstance(filters, str):
        filters = json.loads(filters)

    # Get searchfields from meta and use in Item Link field query
    meta = frappe.get_meta(doctype, cached=True)
    searchfields = meta.get_search_fields()

    columns = ""

    searchfields = searchfields + [
        field
        for field in [searchfield or "name"]
        if field not in searchfields
    ]
    searchfields = " or ".join([f"`tab{doctype}`." + field + " like %(txt)s" for field in searchfields])

    if filters and isinstance(filters, dict):
        if filters.get("item"):
            item_group = frappe.get_cached_value("Item", filters.get("item"), "item_group")
            if not item_group:
                frappe.throw("Item doesn't have Item Group")

            filters["item_group"] = item_group

            del filters["item"]
        else:
            filters.pop("item", None)

    description_cond = ""

    return frappe.db.sql(
        """select
            `tabPerintah Produksi`.name {columns}
        from `tabPerintah Produksi`
        join `tabPerintah Produksi Item` on `tabPerintah Produksi Item`.parent = `tabPerintah Produksi`.name
        where `tabPerintah Produksi`.docstatus < 2
            and `tabPerintah Produksi`.disabled=0
            and {scond}
            {fcond} {mcond}
        order by
            if(locate(%(_txt)s, `tabPerintah Produksi`.name), locate(%(_txt)s, `tabPerintah Produksi`.name), 99999),
            name
        limit %(start)s, %(page_len)s """.format(
            columns=columns,
            scond=searchfields,
            fcond=get_filters_cond("Perintah Produksi Item", filters, conditions, True).replace("%", "%%"),
            mcond=get_match_cond(doctype).replace("%", "%%"),
            description_cond=description_cond,
        ),
        {
            "today": nowdate(),
            "txt": "%%%s%%" % txt,
            "_txt": txt.replace("%", ""),
            "start": start,
            "page_len": page_len,
        },
        as_dict=as_dict,
    )

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_batch_no(doctype, txt, searchfield, start, page_len, filters):
    doctype = "Batch"
    meta = frappe.get_meta(doctype, cached=True)
    searchfields = meta.get_search_fields()
    page_len = 30

    from erpnext.controllers.queries import (
        get_batches_from_stock_ledger_entries, get_batches_from_serial_and_batch_bundle,
        get_empty_batches
    )

    batches = get_batches_from_stock_ledger_entries(searchfields, txt, filters, start, page_len)
    batches.extend(get_batches_from_serial_and_batch_bundle(searchfields, txt, filters, start, page_len))

    filtered_batches = get_filterd_batches(batches, filters)

    if filters.get("is_inward"):
        filtered_batches.extend(get_empty_batches(filters, start, page_len, filtered_batches, txt))

    return filtered_batches

def get_ste_draft(batches, batch_no, filters):
    warehouse = filters.get("warehouse")
    detail_name = filters.get("detail_name")
    
    sted = frappe.qb.DocType("Stock Entry Detail")

    query = (
        frappe.qb.from_(sted)
        .select(
            sted.batch_no,
            sted.s_warehouse,
            sted.t_warehouse,
            sted.parent,
            fn.Sum(sted.qty).as_("actual_qty"),
        )
        .where(
            (sted.docstatus < 1)
            & (sted.name != detail_name)
            & (sted.batch_no.isin(batch_no))
            & ((sted.s_warehouse == warehouse) | (sted.t_warehouse == warehouse))
        )
        .groupby(sted.batch_no, sted.parent)
    )

    for d in query.run(as_dict=True):
        # item_map = iwb_map.setdefault(d.item_code, {})
        if d.s_warehouse and d.s_warehouse == warehouse:
            batches[d.batch_no][1] -= d.actual_qty

        if d.t_warehouse and d.t_warehouse == warehouse:
            batches[d.batch_no][1] += d.actual_qty
               
def get_filterd_batches(data, filters):
    batches = OrderedDict()

    for batch_data in data:
        if batch_data[0] not in batches:
            batches[batch_data[0]] = list(batch_data)
        else:
            batches[batch_data[0]][1] += batch_data[1]

    if batches:
        get_ste_draft(batches, list(batches.keys()), filters)
    
    filterd_batch = []
    for _batch, batch_data in batches.items():
        if batch_data[1] > 0:
            filterd_batch.append(tuple(batch_data))

    return filterd_batch