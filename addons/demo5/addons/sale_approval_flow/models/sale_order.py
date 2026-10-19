from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

PROTECTED_FIELDS = {'is_approved', 'approved_by', 'approved_date', 'approved_amount'}
APPROVER_GROUP = 'sale_approval_flow.group_so_approver'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    special_instructions = fields.Text(help="Printed on the quotation / order PDF.")
    needs_approval = fields.Boolean(compute='_compute_needs_approval')
    is_approved = fields.Boolean(readonly=True, copy=False, tracking=True)
    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    approved_date = fields.Datetime(readonly=True, copy=False)
    approved_amount = fields.Monetary(readonly=True, copy=False, currency_field='currency_id')

    @api.model
    def _approval_threshold(self):
        value = self.env['ir.config_parameter'].sudo().get_param('sale_approval_flow.threshold', '0')
        try:
            return float(value)
        except ValueError:
            return 0.0

    @api.depends('amount_total', 'currency_id', 'company_id', 'date_order')
    def _compute_needs_approval(self):
        threshold = self._approval_threshold()
        for order in self:
            amount = order.amount_total
            company = order.company_id
            if order.currency_id and company and order.currency_id != company.currency_id:
                date = (order.date_order or fields.Datetime.now()).date()
                amount = order.currency_id._convert(amount, company.currency_id, company, date)
            order.needs_approval = threshold > 0 and amount > threshold

    # ---- the approval fields cannot be forged --------------------------
    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            if any(PROTECTED_FIELDS & set(vals) for vals in vals_list):
                raise AccessError(_("Approval fields can only be changed through the Approve action."))
            context = {key: value for key, value in self.env.context.items()
                       if not (key.startswith('default_') and key[len('default_'):] in PROTECTED_FIELDS)}
            self = self.with_context(context)
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and PROTECTED_FIELDS & set(vals):
            raise AccessError(_("Approval fields can only be changed through the Approve action."))
        result = super().write(vals)
        # An approval is only valid for the amount that was approved.
        stale = self.filtered(
            lambda o: o.is_approved and o.state in ('draft', 'sent')
            and o.currency_id.compare_amounts(o.amount_total, o.approved_amount) != 0
        )
        if stale:
            stale.sudo().write({
                'is_approved': False,
                'approved_by': False,
                'approved_date': False,
                'approved_amount': 0.0,
            })
            for order in stale:
                order.message_post(body=_("The order amount changed after approval. The approval was removed."))
        return result

    # ---- actions -------------------------------------------------------
    def _check_is_approver(self):
        if not self.env.user.has_group(APPROVER_GROUP):
            raise AccessError(_("Only users in the Sales Order Approval / Approver group can do this."))

    def action_approve(self):
        self._check_is_approver()
        orders = self.filtered(lambda o: o.state in ('draft', 'sent') and o.needs_approval and not o.is_approved)
        if not orders:
            raise UserError(_("There is no order here that is waiting for approval."))
        for order in orders:
            order.sudo().write({
                'is_approved': True,
                'approved_by': self.env.user.id,
                'approved_date': fields.Datetime.now(),
                'approved_amount': order.amount_total,
            })
            order.message_post(body=_("Order approved by %s.", self.env.user.name))
        return True

    def action_revoke_approval(self):
        self._check_is_approver()
        orders = self.filtered(lambda o: o.state in ('draft', 'sent') and o.is_approved)
        if not orders:
            raise UserError(_("There is no approved quotation to revoke."))
        orders.sudo().write({
            'is_approved': False,
            'approved_by': False,
            'approved_date': False,
            'approved_amount': 0.0,
        })
        for order in orders:
            order.message_post(body=_("Approval revoked by %s.", self.env.user.name))
        return True

    def action_confirm(self):
        for order in self:
            if order.needs_approval and not order.is_approved:
                raise UserError(_(
                    "Order %(name)s is above the approval limit and has not been approved yet.",
                    name=order.name,
                ))
        return super().action_confirm()
