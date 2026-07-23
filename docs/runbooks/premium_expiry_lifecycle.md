# Premium expiry lifecycle runbook

## Scope

The lifecycle task transitions only `ACTIVE` `PREMIUM` entitlements with a
non-null `ends_at <= now` to `EXPIRED`.

Each invocation processes one bounded batch. The default batch size is `500`,
the accepted runtime range is `1..5000`, and repeated invocations drain the
remaining due rows. Candidate rows are claimed with `FOR UPDATE SKIP LOCKED`,
so concurrent workers do not wait on or update the same locked rows.

## Default state

The hourly Celery schedule and its critical-task heartbeat registry entry are
both absent by default. They are registered only when
`PREMIUM_EXPIRY_SCHEDULE_ENABLED=true`.

This repository change does not enable the flag in production configuration
and does not perform a production task run.

## Controlled task

After a separately approved configuration change, Celery beat registers:

```text
app.workers.tasks.premium_expiry.expire_premium_entitlements
```

with schedule key `premium-expiry-lifecycle-hourly`.

## Verification

Verify that:

- only `entitlement_type = 'PREMIUM'` and `status = 'ACTIVE'` rows changed;
- every changed row had a non-null `ends_at <= task start time`;
- unaffected statuses, other entitlement types, future end dates and null end
  dates remain unchanged;
- the remaining due count decreases across bounded batches;
- the task heartbeat uses the same schedule key as Celery beat.

## Disable and recovery

Disable the schedule through a separate approved configuration change. Do not
manually update entitlements, alter payment states, or run a data backfill
without a separately reviewed recovery plan.
