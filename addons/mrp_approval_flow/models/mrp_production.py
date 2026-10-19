from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

APPROVER_GROUP = 'mrp_approval_flow.group_mo_approver'
PROTECTED_FIELDS = ('approval_state', 'approved_by', 'approved_date')


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
    approval_log_ids = fields.One2many(
        'mrp.approval.log',
        'production_id',
        string='Approval Log',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Protection of the approval fields
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        # Nobody can create an order that is already approved; the
        # approval fields are only written through action_approve().
        if not self.env.su:
            vals_list = [
                {k: v for k, v in vals.items() if k not in PROTECTED_FIELDS}
                for vals in vals_list
            ]
        return super().create(vals_list)

    def write(self, vals):
        if (
            not self.env.su
            and not self.env.context.get('mrp_approval_internal')
            and any(field in vals for field in PROTECTED_FIELDS)
        ):
            raise AccessError(
                _("Approval fields can only be changed with the Approve or Revoke buttons.")
            )
        return super().write(vals)

    # ------------------------------------------------------------------
    # Approval actions
    # ------------------------------------------------------------------
    def _check_is_approver(self) -> None:
        if not self.env.user.has_group(APPROVER_GROUP):
            raise AccessError(
                _("Only users in the MO Approval / Approver group can do this.")
            )

    def action_approve(self):
        self._check_is_approver()
        finished = self.filtered(lambda mo: mo.state in ('done', 'cancel'))
        if finished:
            raise UserError(
                _("Finished or cancelled orders cannot be approved: %s",
                  ", ".join(finished.mapped('name')))
            )
        to_approve = self.filtered(lambda mo: mo.approval_state != 'approved')
        to_approve.with_context(mrp_approval_internal=True).write({
            'approval_state': 'approved',
            'approved_by': self.env.user.id,
            'approved_date': fields.Datetime.now(),
        })
        self.env['mrp.approval.log'].create([
            {'production_id': mo.id, 'action': 'approved'} for mo in to_approve
        ])
        return True

    def action_revoke_approval(self):
        self._check_is_approver()
        started = self.filtered(lambda mo: mo.state not in ('draft', 'confirmed'))
        if started:
            raise UserError(
                _("Approval can only be revoked before production starts: %s",
                  ", ".join(started.mapped('name')))
            )
        to_revoke = self.filtered(lambda mo: mo.approval_state == 'approved')
        to_revoke.with_context(mrp_approval_internal=True).write({
            'approval_state': 'pending',
            'approved_by': False,
            'approved_date': False,
        })
        self.env['mrp.approval.log'].create([
            {'production_id': mo.id, 'action': 'revoked'} for mo in to_revoke
        ])
        return True

    # ------------------------------------------------------------------
    # The gate: production cannot start or finish without approval.
    # Confirming is intentionally NOT blocked, because sales orders and
    # replenishment rules confirm manufacturing orders automatically.
    # ------------------------------------------------------------------
    def _check_approved(self) -> None:
        pending = self.filtered(lambda mo: mo.approval_state != 'approved')
        if pending:
            raise UserError(
                _("These manufacturing orders need approval before production can start or finish: %s",
                  ", ".join(pending.mapped('name')))
            )

    def action_start(self):
        self._check_approved()
        return super().action_start()

    def button_mark_done(self):
        self._check_approved()
        return super().button_mark_done()
