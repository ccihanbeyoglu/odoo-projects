from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestMrpApprovalFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester = new_test_user(
            cls.env,
            login='mo_requester',
            groups='base.group_user,mrp_approval_flow.group_mo_requester',
        )
        cls.approver = new_test_user(
            cls.env,
            login='mo_approver',
            groups='base.group_user,mrp_approval_flow.group_mo_approver',
        )
        cls.product = cls.env['product.product'].create({
            'name': 'Approval Test Product',
            'type': 'consu',
            'is_storable': True,
        })
        cls.mo = cls.env['mrp.production'].create({
            'product_id': cls.product.id,
            'product_qty': 1.0,
        })

    def _confirmed_mo(self):
        self.mo.action_confirm()
        self.assertEqual(self.mo.state, 'confirmed')
        return self.mo

    def test_new_order_is_pending(self):
        self.assertEqual(self.mo.approval_state, 'pending')

    def test_confirm_is_not_blocked(self):
        # Sales orders and replenishment confirm orders automatically.
        self.mo.with_user(self.requester).action_confirm()
        self.assertEqual(self.mo.state, 'confirmed')

    def test_start_blocked_until_approved(self):
        mo = self._confirmed_mo()
        with self.assertRaises(UserError):
            mo.action_start()
        self.assertEqual(mo.state, 'confirmed')

    def test_finish_blocked_until_approved(self):
        mo = self._confirmed_mo()
        with self.assertRaises(UserError):
            mo.button_mark_done()

    def test_requester_cannot_approve(self):
        with self.assertRaises(AccessError):
            self.mo.with_user(self.requester).action_approve()
        self.assertEqual(self.mo.approval_state, 'pending')

    def test_approver_approves_and_production_can_start(self):
        mo = self._confirmed_mo()
        mo.with_user(self.approver).action_approve()
        self.assertEqual(mo.approval_state, 'approved')
        self.assertEqual(mo.approved_by, self.approver)
        self.assertTrue(mo.approved_date)
        mo.action_start()
        self.assertEqual(mo.state, 'progress')

    def test_log_is_written_for_approve_and_revoke(self):
        self.mo.with_user(self.approver).action_approve()
        self.mo.with_user(self.approver).action_revoke_approval()
        actions = self.mo.approval_log_ids.mapped('action')
        self.assertCountEqual(actions, ['approved', 'revoked'])
        users = self.mo.approval_log_ids.mapped('user_id')
        self.assertEqual(users, self.approver)

    def test_revoke_blocks_start_again(self):
        mo = self._confirmed_mo()
        mo.with_user(self.approver).action_approve()
        mo.with_user(self.approver).action_revoke_approval()
        self.assertEqual(mo.approval_state, 'pending')
        self.assertFalse(mo.approved_by)
        with self.assertRaises(UserError):
            mo.action_start()

    def test_approval_fields_cannot_be_written_directly(self):
        with self.assertRaises(AccessError):
            self.mo.with_user(self.requester).write({'approval_state': 'approved'})
        with self.assertRaises(AccessError):
            self.mo.with_user(self.approver).write({'approval_state': 'approved'})

    def test_cannot_create_an_order_that_is_already_approved(self):
        mo = self.env['mrp.production'].with_user(self.requester).create({
            'product_id': self.product.id,
            'product_qty': 1.0,
            'approval_state': 'approved',
        })
        self.assertEqual(mo.approval_state, 'pending')

    def test_copy_does_not_keep_approval(self):
        self.mo.with_user(self.approver).action_approve()
        copy = self.mo.copy()
        self.assertEqual(copy.approval_state, 'pending')
        self.assertFalse(copy.approved_by)

    def test_log_entries_are_immutable(self):
        self.mo.with_user(self.approver).action_approve()
        with self.assertRaises(UserError):
            self.mo.approval_log_ids.write({'action': 'revoked'})
