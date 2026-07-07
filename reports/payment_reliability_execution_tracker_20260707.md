# Payment Reliability Execution Tracker - Telegram Stars / Premium Purchases

Date: 2026-07-07
Working branch: `feature/arena-monetization-pr`
Plan: `reports/payment_reliability_plan_20260707.md`
Production incident SHA: `1fb8a09`
Local baseline SHA: `7c0590a93c56849fae680b14508ec6531cc30f3f`

## Execution rules

- No deploy.
- No production DB writes.
- No `.env*`, secret, deploy, or protected branch changes.
- No merge to `main`.
- Use small independent patches.
- Each patch must have targeted tests/checks, one commit, then independent audit.
- If audit returns `FAIL`, stop the next phase until fixed or blocked.
- Auto-recovery must remain disabled by default and dry-run first.

## Independent auditor

- Auditor Agent: `Ramanujan`
- Role: read-only patch reviewer.
- Scope: compare each commit/diff against the Payment Reliability Plan and this tracker.
- Checks: production safety, idempotency, test coverage, migration safety, secret leakage,
  Telegram Stars correctness, and regression risk.
- Verdicts allowed: `PASS`, `PASS_WITH_NOTES`, `FAIL`.

## Current code map

### Webhook and update processing

- `app/main.py`: includes the Telegram webhook router.
- `app/api/routes/telegram_webhook.py`: handles `POST /webhook/telegram`, validates
  `X-Telegram-Bot-Api-Secret-Token`, parses JSON, extracts `update_id`, enqueues
  `process_telegram_update`, and returns `503` when enqueue fails.
- `app/services/telegram_updates.py`: update id extraction and webhook secret validation.
- `app/workers/tasks/telegram_updates.py`: Celery task entrypoint.
- `app/workers/tasks/telegram_updates_processing.py`: processed-update idempotency and
  dispatcher feed.
- `app/db/models/processed_updates.py`: update-level idempotency status only; it does not
  store raw payment update evidence.

### Payment handlers and purchase flow

- `app/bot/application.py`: registers `payments_router`.
- `app/bot/handlers/payments.py`: buy callback, pre-checkout handler, successful payment
  handler.
- `app/bot/handlers/payments_buy.py`: buy flow helpers.
- `app/bot/handlers/payments_buy_flow.py`: purchase initialization orchestration.
- `app/bot/handlers/payments_buy_completion.py`: Telegram Stars invoice send and invoice
  sent marking.
- `app/bot/handlers/payments_runtime.py`: maps Telegram user/payment objects into
  `PurchaseService` calls.
- `app/economy/purchases/service/precheckout.py`: pre-checkout validation.
- `app/economy/purchases/service/credit.py`: successful payment paid marker plus immediate
  asset crediting.
- `app/economy/purchases/service/credit_assets.py`: entitlement, wallet/streak/ticket/promo,
  ledger credit, and final `CREDITED` status.
- `app/economy/purchases/service/entitlements.py`: premium entitlement creation/update.

### Recovery, reconciliation, and alerts

- `app/workers/tasks/payments_reliability_async.py`: stale invoice expiry, stale
  `PAID_UNCREDITED` recovery, promo rollback, existing alert on review/errors.
- `app/workers/tasks/payments_reliability_reconciliation.py`: internal DB paid-vs-ledger
  reconciliation only; no Telegram `getStarTransactions`.
- `app/workers/tasks/payments_reliability_schedule.py`: beat schedule for payment
  reliability tasks.
- `app/services/payments_reliability.py`: reconciliation diff helpers.
- `app/services/alerts.py`: ops alert facade.
- `docs/operations/production_state_checks.md`: production read-only status checklist.
- `docs/runbooks/telegram_sandbox_stars_smoke.md`: sandbox Stars smoke runbook.

### Relevant tests

- `tests/api/test_telegram_webhook.py`
- `tests/bot/test_payments_handler_flow.py`
- `tests/economy/test_purchase_credit_service.py`
- `tests/integration/test_purchase_premium_integration.py`
- `tests/integration/test_payments_idempotency_purchase_flow_integration.py`
- `tests/integration/test_payments_idempotency_recovery_integration.py`
- `tests/integration/test_payments_idempotency_reconciliation_integration.py`
- `tests/economy/test_purchase_refund_state_units.py`
- `tests/integration/test_purchase_refund_integration.py`
- `tests/services/test_payments_reliability.py`
- `tests/workers/test_payments_reliability_async.py`

## Phase status

| Phase | Goal | Status | Notes |
|---|---|---:|---|
| 0 | Baseline and safety tracker | AUDIT | Tracker created; targeted baseline checks passed. |
| 1 | Read-only invariant checker and allowed_updates verification | TODO | No behavior changes; script and unit tests only. |
| 2 | Payment-specific observability and alerts | TODO | Structured logs, read-only scheduled alerts, docs. |
| 3 | Telegram Stars client and reconciliation dry-run | TODO | Feature-flagged, dry-run, no auto-credit. |
| 4 | Review records / persistent reconciliation findings | TODO | Migration only after safety/data audit or documented deferral. |
| 5 | Exact-match auto-recovery behind feature flag | TODO | Disabled by default; strict exact-match criteria. |
| 6 | Durable payment inbox / payment events | TODO | Only after prior phases are stable. |
| 7 | Idempotent asset crediting and stronger DB constraints | TODO | Constraints only after data audit. |
| 8 | Production smoke and final hardening | TODO | Safe smoke/runbook, no deploy. |

## Planned patch ledger

| Patch | Phase | Target | Status | Commit | Tests/evidence | Auditor verdict | Lead response |
|---|---:|---|---:|---|---|---|---|
| P0 | 0 | Add execution tracker and baseline code map | AUDIT | Pending | `.venv/bin/python -m pytest --capture=no -q --ignore=tests/integration tests/api/test_telegram_webhook.py tests/bot/test_payments_handler_flow.py tests/economy/test_purchase_credit_service.py tests/services/test_payments_reliability.py tests/workers/test_payments_reliability_async.py` -> `30 passed in 14.32s` | Pending | Pending |
| P1A | 1 | Unit coverage for payment invariant checks and allowed_updates helper | TODO | Pending | Pending | Pending | Pending |
| P1B | 1 | `scripts/payment_reliability_checks.py` read-only checker | TODO | Pending | Pending | Pending | Pending |
| P2A | 2 | Structured payment logs without sensitive payloads | TODO | Pending | Pending | Pending | Pending |
| P2B | 2 | Read-only invariant alerts in scheduled reliability path | TODO | Pending | Pending | Pending | Pending |
| P2C | 2 | Production state and sandbox Stars runbook updates | TODO | Pending | Pending | Pending | Pending |
| P3A | 3 | Telegram Stars API wrapper with safe timeout/error handling | TODO | Pending | Pending | Pending | Pending |
| P3B | 3 | Dry-run reconciliation classifier and safe feature flags | TODO | Pending | Pending | Pending | Pending |
| P3C | 3 | Disabled/dry-run Celery wiring | TODO | Pending | Pending | Pending | Pending |
| P4 | 4 | Persistent review records or documented migration deferral | TODO | Pending | Pending | Pending | Pending |
| P5 | 5 | Exact-match auto-recovery behind safe flags | TODO | Pending | Pending | Pending | Pending |
| P6 | 6 | Durable payment update inbox and replay path | TODO | Pending | Pending | Pending | Pending |
| P7A | 7 | Idempotent premium entitlement and ledger credit re-entry | TODO | Pending | Pending | Pending | Pending |
| P7B | 7 | Data-audited DB constraints if approved | TODO | Pending | Pending | Pending | Pending |
| P8 | 8 | Payment smoke and final reliability runbook | TODO | Pending | Pending | Pending | Pending |

## Baseline checks

- `git rev-parse HEAD` -> `7c0590a93c56849fae680b14508ec6531cc30f3f`.
- `.agent/project` has no `[FILL_PER_PROJECT]` placeholders.
- Targeted baseline:
  - Command: `.venv/bin/python -m pytest --capture=no -q --ignore=tests/integration tests/api/test_telegram_webhook.py tests/bot/test_payments_handler_flow.py tests/economy/test_purchase_credit_service.py tests/services/test_payments_reliability.py tests/workers/test_payments_reliability_async.py`
  - Result: `30 passed in 14.32s`.

## Audit log

Pending first commit.

## Open owner decisions

- Whether to commit `PAID_UNCREDITED` before crediting in normal successful-payment flow.
- Whether durable webhook storage should cover all updates or only payment-relevant updates.
- Payment audit retention period.
- Manual compensation model and refund policy after compensation.
- Auto-recovery enablement soak gate duration.
- Telegram Stars API implementation choice if aiogram lacks typed support.
