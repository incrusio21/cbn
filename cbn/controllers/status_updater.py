# Copyright (c) 2024, DAS and Contributors
# License: GNU General Public License v3. See license.txt

import frappe

def update_prev_doc(self, args):
    if self.docstatus == 1:
        args["cond"] = " or name='%s'" % self.name.replace('"', '"')
    else:
        args["cond"] = " and name!='%s'" % self.name.replace('"', '"')

    # updates qty in the child table
    args["detail_id"] = self.get(args["join_field"])

    if not args.get("update_modified"):
        args["update_modified"] = ""

    if args["detail_id"]:
        if not args.get("extra_cond"):
            args["extra_cond"] = ""
                                        
        args["source_dt_value"] = (
            frappe.db.sql(
                """
                (select ifnull(sum({source_field}), 0)
                    from `tab{source_dt}` where `{join_field}`='{detail_id}'
                    and (docstatus=1 {cond}) {extra_cond})
        """.format(**args)
            )[0][0]
            or 0.0
        )
	
        frappe.db.sql(
            """update `tab{target_dt}`
            set {target_field} = {source_dt_value} {update_modified}
            where name='{detail_id}'""".format(**args)
        )

    if "percent_join_field" in args:
        update_percent_prev_doc(self, args)

def update_percent_prev_doc(self, args):
    args["name"] = self.get(args["percent_join_field"])

    if not args.get("extra_parent_cond"):
        args["extra_parent_cond"] = ""

    frappe.db.sql(
        """update `tab{target_parent_dt}`
        set {target_parent_field} = round(
            ifnull((select
                ifnull(sum(case when abs({target_ref_field}) > abs({target_field}) then abs({target_field}) else abs({target_ref_field}) end), 0)
                / sum(abs({target_ref_field})) * 100
            from `tab{target_dt}` where parent='{name}' and parenttype='{target_parent_dt}' {extra_parent_cond} having sum(abs({target_ref_field})) > 0), 0), 6)
            {update_modified}
        where name='{name}'""".format(**args)
    )