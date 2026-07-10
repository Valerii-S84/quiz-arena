# Premium expiry lifecycle runbook

## Symptom

Checker reports `expired_active_entitlements_count`.

## Checker

```bash
.venv/bin/python scripts/production_critical_invariants.py --json
```

## Severity

`P2` by default because effective premium lookup is time-aware. Escalate to `P1` if expired `ACTIVE` rows block new premium grants, create false entitlement display, or correlate with payment failures.

## Owner Semantics

Preferred lifecycle is implemented in code:
- expired `ACTIVE` premium entitlement rows can be transitioned to `EXPIRED`;
- task is idempotent;
- effective lookup still requires `starts_at <= now` and `ends_at > now`;
- no production task run is performed by this PR.

## What To Check

- `entitlements.entitlement_type = 'PREMIUM'`
- `status`
- `starts_at`
- `ends_at`
- `source_purchase_id`
- whether user has a newer effective premium entitlement.

## Do Not Do Without Approval

- Do not run the expiry task on production before migration/deploy approval.
- Do not manually update entitlements.
- Do not revoke purchase-linked rows.
- Do not change payment status to compensate for entitlement state.

## Controlled Task

After controlled deploy and approval, the scheduled task is:

```python
app.workers.tasks.premium_expiry.expire_premium_entitlements
```

It marks only `ACTIVE` `PREMIUM` rows with `ends_at <= now` as `EXPIRED`.

## Escalation

Escalate when:
- expired rows are numerous;
- a paid user lacks effective entitlement;
- a new premium purchase is blocked;
- refund/payment semantics are unclear.

## Rollback / Disable

If expiry transition is suspected to be wrong, stop the scheduled task through a separate approved deploy/config change and use DB backup/review before any data repair.
