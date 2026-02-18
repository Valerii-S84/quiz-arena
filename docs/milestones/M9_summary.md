# M9 Summary

## Implemented
- Added referral domain module:
  - `app/economy/referrals/service.py`
  - `app/economy/referrals/constants.py`
- Implemented referral start tracking from Telegram deep-link payload:
  - `/start ref_<code>` payload is parsed in `app/bot/handlers/start.py`;
  - new user onboarding now accepts `start_payload` and registers referral start.
- Added referral persistence/query layer:
  - `app/db/repo/referrals_repo.py`
  - extended helper queries in existing repos (`quiz_attempts`, `mode_access`).
- Implemented anti-fraud controls:
  - self-referral guard;
  - cyclic pair guard (`A->B` and `B->A`) within 30 days -> `REJECTED_FRAUD`;
  - velocity guard (`>10` referral starts/day per referrer) -> `REJECTED_FRAUD`.
- Implemented qualification checks:
  - invited user must reach 20 quiz attempts in 14 days;
  - activity must span at least 2 Berlin-local days;
  - deleted referred user is canceled (`CANCELED`).
- Implemented reward distribution:
  - one reward per each 3 qualified referrals;
  - 48h reward delay after each qualification milestone;
  - max 2 referral rewards per Berlin calendar month;
  - overflow becomes `DEFERRED_LIMIT` and is re-evaluated later.
- Implemented operational scheduling (Celery):
  - qualification checks every 10 minutes;
  - reward distribution every 15 minutes;
  - deferred rollover re-check at 00:05 Berlin on day 1 of month.
- Added referral reward application pipeline:
  - default reward grant implemented as `MEGA_PACK_15` equivalent (+15 paid energy + 24h mode access grant);
  - premium-starter reward grant path is also implemented in domain service.

## Not Implemented
- User-facing reward choice UX (`Mega Pack` vs `Premium Starter`) is not yet wired into bot handlers; default automatic reward path is used.
- Dedicated manual review UI/dashboard for fraud investigation and threshold tuning is not implemented.
- External notification channel for referral milestone/reward events is not implemented.

## Risks
- Referral reward choice is currently not interactive; business may require explicit user selection before production.
- Qualification and reward jobs currently scan DB in periodic batches; high-scale optimization (partitioning/index tuning/aggregation cache) may be required.

## Decisions
- Reward issuance is anchored to every 3rd qualified referral in chronological order; this enforces deterministic 48h delay from milestone reach.
- Deferred-limit handling is status-driven (`DEFERRED_LIMIT`) in `referrals` table and reprocessed by scheduled reward job.
