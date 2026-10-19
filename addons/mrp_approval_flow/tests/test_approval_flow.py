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
        # A manufacturing user who is not in any of the new groups.
        cls.plain_user = new_test_user(
            cls.env,
            login='mo_plain',
            groups='base.group_user,mrp.group_mrp_user',
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

    def _new_mo(self):
        return self.env['mrp.production'].create({
            'product_id': self.product.id,
            'product_qty': 1.0,
        })

    def _confirmed_mo(self):
        self.mo.action_confirm()
        self.assertEqual(self.mo.state, 'confirmed')
        return self.mo

    # ---- default behaviour ---------------------------------------------
    def test_new_order_is_pending(self):
        self.assertEqual(self.mo.approval_state, 'pending')

    def test_confirm_is_not_blocked(self):
        # Sales orders and replenishment confirm orders automatically.
        self.mo.with_user(self.requester).action_confirm()
        self.assertEqual(self.mo.state, 'confirmed')

    def test_admin_is_an_approver_after_install(self):
        self.assertTrue(self.env.ref('base.user_admin').has_group('mrp_approval_flow.group_mo_approver'))

    # ---- the gate ------------------------------------------------------
    def test_start_blocked_until_approved(self):
        mo = self._confirmed_mo()
        with self.assertRaises(UserError):
            mo.action_start()
        self.assertEqual(mo.state, 'confirmed')

    def test_finish_blocked_until_approved(self):
        mo = self._confirmed_mo()
        with self.assertRaises(UserError):
            mo.button_mark_done()

    def test_workorder_start_blocked_until_approved(self):
        workcenter = self.env['mrp.workcenter'].create({'name': 'Approval Test WC'})
        bom = self.env['mrp.bom'].create({
            'product_tmpl_id': self.product.product_tmpl_id.id,
            'product_qty': 1.0,
            'operation_ids': [(0, 0, {
                'name': 'Approval Test Operation',
                'workcenter_id': workcenter.id,
                'time_cycle_manual': 1.0,
            })],
        })
        mo = self.env['mrp.production'].create({
            'product_id': self.product.id,
            'product_qty': 1.0,
            'bom_id': bom.id,
        })
        mo.action_confirm()
        workorder = mo.workorder_ids
        self.assertTrue(workorder)
        with self.assertRaises(UserError):
            workorder.button_start()
        mo.with_user(self.approver).action_approve()
        workorder.button_start()
        self.assertEqual(workorder.state, 'progress')

    # ---- who can approve -----------------------------------------------
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

    def test_revoke_blocks_start_again(self):
        mo = self._confirmed_mo()
        mo.with_user(self.approver).action_approve()
        mo.with_user(self.approver).action_revoke_approval()
        self.assertEqual(mo.approval_state, 'pending')
        self.assertFalse(mo.approved_by)
        with self.assertRaises(UserError):
            mo.action_start()

    def test_cannot_approve_finished_order(self):
        mo = self._new_mo()
        mo.action_cancel()
        with self.assertRaises(UserError):
            mo.with_user(self.approver).action_approve()

    def test_cannot_revoke_after_production_started(self):
        mo = self._confirmed_mo()
        mo.with_user(self.approver).action_approve()
        mo.action_start()
        with self.assertRaises(UserError):
            mo.with_user(self.approver).action_revoke_approval()

    def test_mixed_batch_revoke_only_touches_approved_orders(self):
        approved = self._new_mo()
        pending = self._new_mo()
        approved.with_user(self.approver).action_approve()
        (approved | pending).with_user(self.approver).action_revoke_approval()
        self.assertEqual(approved.approval_state, 'pending')
        self.assertEqual(pending.approval_state, 'pending')
        self.assertEqual(len(approved.approval_log_ids), 2)
        self.assertFalse(pending.approval_log_ids)

    # ---- the approval fields cannot be forged --------------------------
    def test_approval_fields_cannot_be_written_directly(self):
        with self.assertRaises(AccessError):
            self.mo.with_user(self.requester).write({'approval_state': 'approved'})
        with self.assertRaises(AccessError):
            self.mo.with_user(self.approver).write({'approval_state': 'approved'})

    def test_forged_context_flag_does_not_help(self):
        mo = self.mo.with_user(self.requester).with_context(mrp_approval_internal=True)
        with self.assertRaises(AccessError):
            mo.write({'approval_state': 'approved'})
        self.assertEqual(self.mo.approval_state, 'pending')

    def test_create_with_approval_values_is_refused(self):
        with self.assertRaises(AccessError):
            self.env['mrp.production'].with_user(self.requester).create({
                'product_id': self.product.id,
                'product_qty': 1.0,
                'approval_state': 'approved',
            })

    def test_default_context_cannot_create_an_approved_order(self):
        mo = self.env['mrp.production'].with_user(self.requester).with_context(
            default_approval_state='approved',
        ).create({
            'product_id': self.product.id,
            'product_qty': 1.0,
        })
        self.assertEqual(mo.approval_state, 'pending')

    def test_copy_does_not_keep_approval(self):
        self.mo.with_user(self.approver).action_approve()
        copy = self.mo.copy()
        self.assertEqual(copy.approval_state, 'pending')
        self.assertFalse(copy.approved_by)

    # ---- the log -------------------------------------------------------
    def test_log_is_written_for_approve_and_revoke(self):
        self.mo.with_user(self.approver).action_approve()
        self.mo.with_user(self.approver).action_revoke_approval()
        actions = self.mo.approval_log_ids.mapped('action')
        self.assertCountEqual(actions, ['approved', 'revoked'])
        self.assertEqual(self.mo.approval_log_ids.mapped('user_id'), self.approver)

    def test_log_cannot_be_forged_by_an_approver(self):
        with self.assertRaises(AccessError):
            self.env['mrp.approval.log'].with_user(self.approver).create({
                'production_id': self.mo.id,
                'user_id': self.requester.id,
                'action': 'approved',
            })

    def test_log_cannot_be_deleted_or_modified(self):
        self.mo.with_user(self.approver).action_approve()
        log = self.mo.approval_log_ids
        with self.assertRaises(AccessError):
            log.with_user(self.approver).unlink()
        with self.assertRaises(UserError):
            log.write({'action': 'revoked'})

    # ---- users who are not in the new groups ---------------------------
    def test_plain_manufacturing_user_can_read_the_order_form_fields(self):
        self.mo.with_user(self.approver).action_approve()
        data = self.mo.with_user(self.plain_user).read(
            ['approval_state', 'approved_by', 'approval_log_ids']
        )
        self.assertEqual(data[0]['approval_state'], 'approved')
        self.assertEqual(len(data[0]['approval_log_ids']), 1)
