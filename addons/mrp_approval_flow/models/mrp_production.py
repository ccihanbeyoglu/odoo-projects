from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

APPROVER_GROUP = 'mrp_approval_flow.group_mo_approver'
PROTECTED_FIELDS = ('approval_state', 'approved_by', 'approved_date')
PROTECTED_DEFAULT_KEYS = tuple(f'default_{name}' for name in PROTECTED_FIELDS)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    approval_state = fields.Selection(
        selection=[
            ('pending', 'Pending Approval'),
            ('approved', 'Approved'),
        ],
        string='Approval Status',
        default='pending',
        readonly=True,
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
    # Protection of the approval fields. Only the approval actions write
    # them, and they do it with sudo(). A normal user cannot approve by
    # sending the values, a default_* context key, or any other context.
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            if any(name in vals for vals in vals_list for name in PROTECTED_FIELDS):
                raise AccessError(
                    _("Approval fields can only be changed with the Approve or Revoke buttons.")
                )
            if any(key in self.env.context for key in PROTECTED_DEFAULT_KEYS):
                clean = {
                    key: value for key, value in self.env.context.items()
                    if key not in PROTECTED_DEFAULT_KEYS
                }
                return super(MrpProduction, self.with_context(clean)).create(vals_list)
        return super().create(vals_list)

    def write(self, vals) -> bool:
        if not self.env.su and any(name in vals for name in PROTECTED_FIELDS):
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

    def action_approve(self) -> bool:
        self._check_is_approver()
        to_approve = self.filtered(lambda mo: mo.approval_state != 'approved')
        finished = to_approve.filtered(lambda mo: mo.state in ('done', 'cancel'))
        if finished:
            raise UserError(
                _("Finished or cancelled orders cannot be approved: %s",
                  ", ".join(finished.mapped('name')))
            )
        to_approve.sudo().write({
            'approval_state': 'approved',
            'approved_by': self.env.user.id,
            'approved_date': fields.Datetime.now(),
        })
        self.env['mrp.approval.log'].sudo().create([
            {'production_id': mo.id, 'user_id': self.env.user.id, 'action': 'approved'}
            for mo in to_approve
        ])
        return True

    def action_revoke_approval(self) -> bool:
        self._check_is_approver()
        to_revoke = self.filtered(lambda mo: mo.approval_state == 'approved')
        started = to_revoke.filtered(lambda mo: mo.state not in ('draft', 'confirmed'))
        if started:
            raise UserError(
                _("Approval can only be revoked before production starts: %s",
                  ", ".join(started.mapped('name')))
            )
        to_revoke.sudo().write({
            'approval_state': 'pending',
            'approved_by': False,
            'approved_date': False,
        })
        self.env['mrp.approval.log'].sudo().create([
            {'production_id': mo.id, 'user_id': self.env.user.id, 'action': 'revoked'}
            for mo in to_revoke
        ])
        return True

    # ------------------------------------------------------------------
    # The gate: the Start button, work order start and mark as done need
    # approval. Confirming is intentionally NOT blocked, because sales
    # orders and replenishment rules confirm manufacturing orders
    # automatically. See the README for what is and is not covered.
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
