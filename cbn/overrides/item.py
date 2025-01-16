# Copyright (c) 2025, DAS and Contributors
# License: GNU General Public License v3. See license.txt

from erpnext.stock.doctype.item.item import Item

class Item(Item):
    
    def clear_retain_sample(self):
        if not (self.has_batch_no or self.custom_has_batch_manufacture):
            self.retain_sample = False

        if not self.retain_sample:
            self.sample_quantity = 0