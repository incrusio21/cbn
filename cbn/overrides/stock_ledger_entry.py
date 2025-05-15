# Copyright (c) 2024, DAS and Contributors
# License: GNU General Public License v3. See license.txt

from erpnext.stock.doctype.stock_ledger_entry.stock_ledger_entry import StockLedgerEntry

from cbn.cbn.batch_manufacture import BatchManufacture

class StockLedgerEntry(StockLedgerEntry):
    
     def on_submit(self):
        super().on_submit()

        if not self.get("via_landed_cost_voucher"):
            BatchManufacture(
				sle=self,
				item_code=self.item_code,
				warehouse=self.warehouse,
				company=self.company
			)
            