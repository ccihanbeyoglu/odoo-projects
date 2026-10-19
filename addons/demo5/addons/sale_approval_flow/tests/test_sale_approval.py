from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSaleApproval(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('sale_approval_flow.threshold', '5000')
        cls.salesman = new_test_user(
            cls.env, login='so_salesman',
            groups='base.group_user,sales_team.group_sale_salesman',
        )
        cls.approver = new_test_user(
            cls.env, login='so_approver',
            groups='base.group_user,sale_approval_flow.group_so_approver',
        )
        cls.partner = cls.env['res.partner'].create({'name': 'Approval Test Customer'})
        cls.product = cls.env['product.product'].create({
            'name': 'Approval Test Service',
            'type': 'service',
            'list_price': 100.0,
        })

    def _order(self, price):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'user_id': self.salesman.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1.0,
                'price_unit': price,
            })],
        })

    # ---- when approval is needed ---------------------------------------
    def test_small_order_needs_no_approval(self):
        order = self._order(1000.0)
        self.assertFalse(order.needs_approval)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_large_order_needs_approval(self):
        self.assertTrue(self._order(6000.0).needs_approval)

    def test_threshold_zero_switches_approval_off(self):
        self.env['ir.config_parameter'].sudo().set_param('sale_approval_flow.threshold', '0')
        order = self._order(900000.0)
        self.assertFalse(order.needs_approval)
        self.env['ir.config_parameter'].sudo().set_param('sale_approval_flow.threshold', '5000')

    # ---- the gate ------------------------------------------------------
    def test_confirm_blocked_until_approved(self):
        order = self._order(6000.0)
        with self.assertRaises(UserError):
            order.with_user(self.salesman).action_confirm()
        self.assertEqual(order.state, 'draft')

    def test_approve_then_confirm(self):
        order = self._order(6000.0)
        order.with_user(self.approver).action_approve()
        self.assertTrue(order.is_approved)
        self.assertEqual(order.approved_by, self.approver)
        order.with_user(self.salesman).action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_salesman_cannot_approve(self):
        order = self._order(6000.0)
        with self.assertRaises(AccessError):
            order.with_user(self.salesman).action_approve()
        self.assertFalse(order.is_approved)

    def test_approving_an_order_below_the_limit_is_refused(self):
        order = self._order(1000.0)
        with self.assertRaises(UserError):
            order.with_user(self.approver).action_approve()

    def test_revoke_blocks_confirm_again(self):
        order = self._order(6000.0)
        order.with_user(self.approver).action_approve()
        order.with_user(self.approver).action_revoke_approval()
        self.assertFalse(order.is_approved)
        with self.assertRaises(UserError):
            order.action_confirm()

    # ---- an approval is only valid for the approved amount -------------
    def test_changing_the_amount_removes_the_approval(self):
        order = self._order(6000.0)
        order.with_user(self.approver).action_approve()
        line = order.order_line
        order.with_user(self.salesman).write({'order_line': [(1, line.id, {'price_unit': 9000.0})]})
        self.assertFalse(order.is_approved)
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_unrelated_edit_keeps_the_approval(self):
        order = self._order(6000.0)
        order.with_user(self.approver).action_approve()
        order.with_user(self.salesman).write({'special_instructions': 'Deliver after 10:00'})
        self.assertTrue(order.is_approved)

    # ---- the approval fields cannot be forged --------------------------
    def test_approval_fields_cannot_be_written_directly(self):
        order = self._order(6000.0)
        with self.assertRaises(AccessError):
            order.with_user(self.salesman).write({'is_approved': True})
        with self.assertRaises(AccessError):
            order.with_user(self.approver).write({'is_approved': True})

    def test_create_with_approval_values_is_refused(self):
        with self.assertRaises(AccessError):
            self.env['sale.order'].with_user(self.salesman).create({
                'partner_id': self.partner.id,
                'is_approved': True,
            })

    def test_default_context_cannot_create_an_approved_order(self):
        order = self.env['sale.order'].with_user(self.salesman).with_context(
            default_is_approved=True,
        ).create({'partner_id': self.partner.id})
        self.assertFalse(order.is_approved)

    def test_copy_does_not_keep_the_approval(self):
        order = self._order(6000.0)
        order.with_user(self.approver).action_approve()
        self.assertFalse(order.copy().is_approved)

    # ---- the PDF -------------------------------------------------------
    def test_pdf_shows_instructions_and_approval(self):
        order = self._order(6000.0)
        order.special_instructions = 'Deliver after 10:00'
        order.with_user(self.approver).action_approve()
        html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder', order.ids)
        self.assertIn(b'Special instructions', html)
        self.assertIn(b'Deliver after 10:00', html)
        self.assertIn(b'Approved by', html)
