# M3 Summary

## Implemented
- Added energy domain module `app/economy/energy/` with constants, types, time helpers, state rules, and service orchestration.
- Implemented state rules for:
  - consume priority (`free -> paid`, premium bypass)
  - regen ticks (`+1 / 1800 sec`, capped)
  - daily top-up to cap by Berlin local date.
- Implemented transactional service methods:
  - `consume_quiz`
  - `credit_paid_energy`
  - `sync_energy_clock`
- Added repository support for M3 service dependencies:
  - `LedgerRepo` for idempotency key checks and inserts.
  - `EntitlementsRepo` for active premium resolution.
- Added state-machine focused unit tests with Berlin-date checks.

## Not Implemented
- Integration tests with real Postgres transactions and concurrent workers.
- Hooking M3 service into bot handlers/webhook flow.
- Premium bypass ledger entry with amount=0 (blocked by current `ledger_entries.amount > 0` constraint).

## Risks
- Idempotency and row-lock behavior is implemented in service flow, but not yet proven on real Postgres runtime.
- Premium bypass audit granularity may need dedicated event table or relaxed ledger rule if zero-amount events must be persisted.

## Decisions
- Kept energy transition logic pure (`rules.py`) and transport-agnostic for deterministic testing.
- Kept service methods async/transaction-friendly with `SELECT ... FOR UPDATE` via repositories.
