from odoo import _, fields, models
from odoo.exceptions import UserError


class MrpApprovalLog(models.Model):
    _name = 'mrp.approval.log'
    _description = 'Manufacturing Order Approval Log'
    _order = 'id desc'

    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    date = fields.Datetime(
        required=True,
        readonly=True,
        default=fields.Datetime.now,
    )
    action = fields.Selection(
        selection=[
            ('approved', 'Approved'),
            ('revoked', 'Approval Revoked'),
        ],
        required=True,
        readonly=True,
    )

    def write(self, vals):
        raise UserError(_("Approval log entries cannot be modified."))
