from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    approval_state = fields.Selection(
        selection=[
            ('pending', 'Pending Approval'),
            ('approved', 'Approved'),
        ],
        string='Approval Status',
        default='pending',
        copy=False,
        tracking=True,
    )
    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        copy=False,
    )
    approved_date = fields.Datetime(
        string='Approved On',
        readonly=True,
        copy=False,
    )
