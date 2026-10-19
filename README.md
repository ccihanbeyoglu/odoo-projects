# odoo-projects

Small Odoo 19 custom modules with automated tests. **Demo / learning projects**, not production-ready products. Each module lives in `addons/` and is covered by `TransactionCase` tests.

| Module | What it does | Tests |
|---|---|---|
| [`mrp_approval_flow`](addons/mrp_approval_flow) | Manufacturing orders need approval before production can start or be finished | 21 |
| [`sale_approval_flow`](addons/sale_approval_flow) | Sales orders above a limit need approval before they can be confirmed; special instructions and approval stamp on the order PDF | 15 |

## mrp_approval_flow
- Every manufacturing order starts as **Pending Approval**. Users in **MO Approval / Approver** can **Approve** it and **Revoke Approval** until production starts.
- Production cannot start (Start button, work order start) or be marked as done until approved.
- Every approval and revocation is written to a log (who, when, what) that cannot be edited or deleted through the UI or RPC.
- Approval fields cannot be written directly, also not with a forged context or `default_*` keys.
- Confirming an order is **not** blocked, because sales orders and replenishment rules confirm orders automatically.

Known limits: other ways of moving an order into progress (recording time, picking components on the shop floor) are not blocked and were not verified on a live database; `button_mark_done` is the hard stop. Subcontracting flows are not supported.

## sale_approval_flow
- A sales order above the configured amount cannot be confirmed until a user in **Sales Order Approval / Approver** approves it. The limit is the system parameter `sale_approval_flow.threshold` (company currency; `0` switches the check off).
- The approval is only valid for the approved amount: if the amount changes before confirmation, the approval is removed and a note is posted in the chatter.
- Approve and Revoke actions are written to the chatter. Approval fields cannot be forged by direct write, create or `default_*` context.
- Adds a **Special instructions** field. The quotation / order PDF shows it, plus an "Approved by ... on ..." line.
- Approvers can see all salespeople's orders (they imply the "all documents" sales group). This was found by the tests.

Known limits: the limit is a single global amount (no per-customer, per-team or per-user rules); the invoice PDF is not changed; flows that confirm orders programmatically through `action_confirm` (for example e-commerce) are blocked the same way and were not tested; not tested with Enterprise or other apps installed.

Ideas for v2: a reason on approve/revoke, a "Waiting for approval" search filter, notifications, multi-level approval, per-team limits, stopping approvers from approving their own orders.

## Run the tests
Tested on Odoo 19.0 Community (docker image `odoo:19.0`, `postgres:16`). In a fresh database:

```
odoo -d test_db -i mrp_approval_flow,sale_approval_flow --test-enable \
  --test-tags post_install/mrp_approval_flow,post_install/sale_approval_flow --stop-after-init
```

Developed in a GitHub Codespace. The default Docker network did not let the containers reach each other there, so both containers were run with `--network host` and `--addons-path=/mnt/extra-addons,...`.

## License
LGPL-3 (see `LICENSE`).
