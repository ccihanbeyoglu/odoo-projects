from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class MrpApprovalLog(models.Model):
    """Who approved or revoked a manufacturing order, and when.

    Entries are written only by the approval actions (with sudo) and cannot
    be changed or deleted through the UI or RPC. They are removed only by
    the database cascade when their manufacturing order is deleted.
    """
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
    company_id = fields.Many2one(
        related='production_id.company_id',
        store=True,
        index=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        readonly=True,
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

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("Approval log entries are written by the approval actions only."))
        return super().create(vals_list)

    def write(self, vals) -> bool:
        raise UserError(_("Approval log entries cannot be modified."))

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("Approval log entries cannot be deleted."))
        return super().unlink()
