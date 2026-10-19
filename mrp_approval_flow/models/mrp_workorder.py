from odoo import models


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def button_start(self, *args, **kwargs):
        # Work orders can start production from the shop floor, so they
        # need the same approval gate as the manufacturing order form.
        self.production_id._check_approved()
        return super().button_start(*args, **kwargs)
