# Payment Reliability Execution Tracker - Telegram Stars / Premium Purchases

Date: 2026-07-07
Working branch: `feature/arena-monetization-pr`
Plan: `reports/payment_reliability_plan_20260707.md` (inspected local planning artifact; left
untracked because it predates the executed patches and its current-state sections are stale)
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
| 0 | Baseline and safety tracker | DONE | Tracker created; targeted baseline checks passed; audit passed with notes. |
| 1 | Read-only invariant checker and allowed_updates verification | DONE | Read-only script, allowed_updates helper, and runbook checks passed audit. |
| 2 | Payment-specific observability and alerts | DONE | Successful-payment logs, invariant alerts, recovery logs, and docs passed audit. |
| 3 | Telegram Stars client and reconciliation dry-run | DONE | Telegram Stars client, conservative dry-run classifier, disabled task wiring, and read-only dry-run runner passed audit. |
| 4 | Review records / persistent reconciliation findings | DONE | Outbox-based OPEN review events and documented migration deferral passed audit; no new migration added. |
| 5 | Exact-match auto-recovery behind feature flag | DONE | Exact-match auto-recovery and transaction revalidation fix passed audit; defaults remain disabled/dry-run. |
| 6 | Durable payment inbox / payment events | DONE | Interim outbox evidence before ACK and documented inbox/payment_events migration deferral passed audit. |
| 7 | Idempotent asset crediting and stronger DB constraints | DONE | P7A idempotent crediting passed audit; P7B `credited_at` preflight was narrowed for legitimate uncredited refunds and passed audit with notes. |
| 8 | Production smoke and final hardening | DONE | Runbooks now require app-level premium lookup proof, safe/off flag confirmation, auto-recovery evidence review, and rollback steps; no production action taken. |

## Planned patch ledger

| Patch | Phase | Target | Status | Commit | Tests/evidence | Auditor verdict | Lead response |
|---|---:|---|---:|---|---|---|---|
| P0 | 0 | Add execution tracker and baseline code map | DONE | `217bdc9` | `.venv/bin/python -m pytest --capture=no -q --ignore=tests/integration tests/api/test_telegram_webhook.py tests/bot/test_payments_handler_flow.py tests/economy/test_purchase_credit_service.py tests/services/test_payments_reliability.py tests/workers/test_payments_reliability_async.py` -> `30 passed in 14.32s` | `PASS_WITH_NOTES` | Accepted; tracker verdict/response recorded after audit. |
| P1A | 1 | `scripts/payment_reliability_checks.py` read-only checker and unit coverage | DONE | `e76b1cc` | `pytest --capture=no -q tests/scripts/test_payment_reliability_checks.py` -> `6 passed`; `ruff check scripts/payment_reliability_checks.py tests/scripts/test_payment_reliability_checks.py` -> pass; `black --check scripts/payment_reliability_checks.py tests/scripts/test_payment_reliability_checks.py` -> pass; `isort --check-only scripts/payment_reliability_checks.py tests/scripts/test_payment_reliability_checks.py` -> pass; `mypy tests/scripts/test_payment_reliability_checks.py` -> pass; CLI `--skip-db --webhook-info-json -` sample -> OK | `PASS_WITH_NOTES` | Accepted; later reconciliation/payment-event checks remain planned for future phases. |
| P1B | 1 | Add allowed_updates verification commands to payment runbooks | DONE | `ca0fc52` | `rg -n "allowed_updates|payment_reliability_checks|message|callback_query|pre_checkout_query" docs/runbooks/telegram_sandbox_stars_smoke.md docs/operations/production_state_checks.md` -> required entries present; `scripts/payment_reliability_checks.py --help` -> documents offline `--webhook-info-json` and `--skip-db` usage | `PASS_WITH_NOTES` | Accepted; docs-only patch did not change runtime behavior. |
| P2A | 2 | Structured successful-payment logs without sensitive payloads | DONE | `6b1705b` | `pytest --capture=no -q tests/bot/test_payments_handler_flow.py tests/economy/test_purchase_credit_service.py` -> `17 passed`; `ruff check app/bot/handlers/payments.py app/economy/purchases/service/credit.py tests/bot/test_payments_handler_flow.py tests/economy/test_purchase_credit_service.py` -> pass; `black --check app/bot/handlers/payments.py app/economy/purchases/service/credit.py tests/bot/test_payments_handler_flow.py tests/economy/test_purchase_credit_service.py` -> pass; `isort --check-only app/bot/handlers/payments.py app/economy/purchases/service/credit.py tests/bot/test_payments_handler_flow.py tests/economy/test_purchase_credit_service.py` -> pass; `mypy app/bot/handlers/payments.py app/economy/purchases/service/credit.py tests/bot/test_payments_handler_flow.py tests/economy/test_purchase_credit_service.py` -> pass | `PASS_WITH_NOTES` | Accepted; `update_id` remains deferred to durable inbox/payment-event phases. |
| P2B | 2 | Read-only invariant alerts in scheduled reliability path | DONE | `a82484d` | `pytest --capture=no -q tests/workers/test_payments_reliability_async.py tests/workers/test_payments_reliability_task.py tests/workers/test_worker_schedule_units.py tests/services/test_alerts.py` -> `22 passed`; `ruff check app/db/repo/purchases_repo.py app/services/alerts_config.py app/workers/tasks/payments_reliability_async.py app/workers/tasks/payments_reliability.py app/workers/tasks/payments_reliability_schedule.py tests/workers/test_payments_reliability_async.py tests/workers/test_payments_reliability_task.py tests/workers/test_worker_schedule_units.py tests/services/test_alerts.py` -> pass; `black --check ...` -> pass; `isort --check-only ...` -> pass; `mypy ...` -> pass | `PASS_WITH_NOTES` | Accepted; repeated Slack/generic alerts while counts remain nonzero are a known non-blocking ops noise risk. |
| P2C | 2 | Structured stale payment recovery logs | DONE | `69512ad` | `pytest --capture=no -q tests/workers/test_payments_reliability_async_credit_batch.py` -> `3 passed`; `ruff check app/workers/tasks/payments_reliability_async.py tests/workers/test_payments_reliability_async_credit_batch.py` -> pass; `black --check app/workers/tasks/payments_reliability_async.py tests/workers/test_payments_reliability_async_credit_batch.py` -> pass; `isort --check-only app/workers/tasks/payments_reliability_async.py tests/workers/test_payments_reliability_async_credit_batch.py` -> pass; `mypy app/workers/tasks/payments_reliability_async.py tests/workers/test_payments_reliability_async_credit_batch.py` -> pass | `PASS_WITH_NOTES` | Accepted; per-purchase warning logs may repeat while recovery remains unresolved. |
| P2D | 2 | Production state, sandbox Stars, and alert catalog docs | DONE | `2b0d7a7` | `rg -n "payment_reliability_checks|payments_precheckout_stuck_detected|payments_paid_uncredited_stuck_detected|payments_credit_invariant_failed|payments_webhook_allowed_updates_missing|run_payment_invariant_alerts|payment_recovery_failed" docs/operations/production_state_checks.md docs/runbooks/telegram_sandbox_stars_smoke.md docs/analytics/events_catalog.md` -> required entries present; `scripts/payment_reliability_checks.py --help` -> documents offline webhook JSON and skip-DB modes | `PASS_WITH_NOTES` | Accepted; event catalog payload/severity detail remains minimal but production checks cover severity/escalation. |
| P3A | 3 | Telegram Stars API wrapper with safe timeout/error handling | FAIL | `bfe751a` | `pytest --capture=no -q tests/services/test_telegram_stars.py` -> `6 passed`; `ruff check app/services/telegram_stars.py tests/services/test_telegram_stars.py` -> pass; `black --check app/services/telegram_stars.py tests/services/test_telegram_stars.py` -> pass; `isort --check-only app/services/telegram_stars.py tests/services/test_telegram_stars.py` -> pass; `mypy app/services/telegram_stars.py tests/services/test_telegram_stars.py` -> pass; official Telegram Bot API checked for `getStarTransactions` parameters and `StarTransaction` fields | `FAIL` | Blocking issue: chained `httpx.HTTPError` could expose token-bearing URL in traceback; fixing in P3A-FIX. |
| P3A-FIX | 3 | Sanitize Telegram Stars HTTP error traceback token exposure | DONE | `1e52b51` | `pytest --capture=no -q tests/services/test_telegram_stars.py` -> `7 passed`; `ruff check app/services/telegram_stars.py tests/services/test_telegram_stars.py` -> pass; `black --check app/services/telegram_stars.py tests/services/test_telegram_stars.py` -> pass; `isort --check-only app/services/telegram_stars.py tests/services/test_telegram_stars.py` -> pass; `mypy app/services/telegram_stars.py tests/services/test_telegram_stars.py` -> pass; traceback-format test confirms token is absent from HTTP status failure traceback | `PASS_WITH_NOTES` | Fixed blocker from P3A; accepted. |
| P3B | 3 | Dry-run reconciliation classifier and safe feature flags | FAIL | `ee3a268` | `pytest --capture=no -q tests/services/test_payment_reconciliation.py tests/services/test_telegram_stars.py` -> `14 passed`; `ruff check app/services/payment_reconciliation.py app/services/telegram_stars.py app/core/config_messaging.py tests/services/test_payment_reconciliation.py tests/services/test_telegram_stars.py` -> pass; `black --check ...` -> pass; `isort --check-only ...` -> pass; `mypy app/services/payment_reconciliation.py app/services/telegram_stars.py app/core/config_messaging.py tests/services/test_payment_reconciliation.py tests/services/test_telegram_stars.py` -> pass | `FAIL` | Blocking issue: exact dry-run match lacked purchase/transaction time-window validation; fixing in P3B-FIX. |
| P3B-FIX | 3 | Add exact-match time-window validation to dry-run classifier | DONE | `fef6760` | `pytest --capture=no -q tests/services/test_payment_reconciliation.py tests/services/test_telegram_stars.py` -> `15 passed`; `ruff check app/services/payment_reconciliation.py app/services/telegram_stars.py app/core/config_messaging.py tests/services/test_payment_reconciliation.py tests/services/test_telegram_stars.py` -> pass; `black --check ...` -> pass; `isort --check-only ...` -> pass; `mypy app/services/payment_reconciliation.py app/services/telegram_stars.py app/core/config_messaging.py tests/services/test_payment_reconciliation.py tests/services/test_telegram_stars.py` -> pass | `PASS_WITH_NOTES` | Fixed blocker from P3B; accepted. Later DB integration must preserve created/precheckout-time and configurable-window intent. |
| P3C | 3 | Disabled/dry-run Celery wiring | DONE | `b1e15f3` | `pytest --capture=no -q tests/workers/test_telegram_stars_reconciliation_task.py tests/workers/test_payments_reliability_task.py tests/workers/test_worker_schedule_units.py tests/workers/test_payments_reliability_async.py` -> `18 passed`; `ruff check app/workers/tasks/payments_reliability_async.py app/workers/tasks/payments_reliability.py app/workers/tasks/payments_reliability_schedule.py tests/workers/test_telegram_stars_reconciliation_task.py tests/workers/test_payments_reliability_task.py tests/workers/test_worker_schedule_units.py` -> pass; `black --check ...` -> pass; `isort --check-only ...` -> pass; `mypy ...` -> pass | `PASS_WITH_NOTES` | Accepted; wiring-only task is safe, and real dry-run comparison remains tracked as P3D. |
| P3D | 3 | Dry-run Stars reconciliation runner without mutations | DONE | `56fa4fb` | `pytest --capture=no -q tests/workers/test_telegram_stars_reconciliation_task.py tests/services/test_payment_reconciliation.py tests/services/test_telegram_stars.py` -> `19 passed`; `pytest --capture=no -q tests/workers/test_payments_reliability_async.py tests/workers/test_payments_reliability_task.py` -> `13 passed`; `ruff check app/db/repo/purchases_repo.py app/workers/tasks/payments_reliability_async.py tests/workers/test_telegram_stars_reconciliation_task.py` -> pass; `black --check ...` -> pass; `isort --check-only ...` -> pass; `mypy app/db/repo/purchases_repo.py app/workers/tasks/payments_reliability_async.py tests/workers/test_telegram_stars_reconciliation_task.py` -> pass | `PASS_WITH_NOTES` | Accepted; persistent checkpoints/review records and dry-run alerts remain tracked for Phase 4. |
| P4A | 4 | Persist Stars dry-run review findings through existing outbox | DONE | `e34bf1e` | `pytest --capture=no -q tests/workers/test_telegram_stars_reconciliation_task.py tests/services/test_payment_reconciliation.py` -> `13 passed`; `pytest --capture=no -q tests/workers/test_payments_reliability_async.py tests/workers/test_payments_reliability_task.py` -> `13 passed`; `ruff check app/db/repo/outbox_events_repo.py app/workers/tasks/payments_reliability_async.py tests/workers/test_telegram_stars_reconciliation_task.py` -> pass; `black --check ...` -> pass; `isort --check-only ...` -> pass; `mypy app/db/repo/outbox_events_repo.py app/workers/tasks/payments_reliability_async.py tests/workers/test_telegram_stars_reconciliation_task.py` -> pass | `PASS_WITH_NOTES` | Accepted; best-effort outbox dedupe is not race-proof without a future unique constraint/review table. |
| P4B | 4 | Document review outbox workflow and migration deferral limits | DONE | `5665a6e` | `rg -n "payments_telegram_stars_reconciliation_review|review_key|transaction_id_hash|raw_payload_stored|candidate_purchase_ids|dedupe|deduplication|OPEN" docs/operations/production_state_checks.md docs/runbooks/telegram_sandbox_stars_smoke.md docs/analytics/events_catalog.md` -> required entries present; `rg -n "bot[0-9]+:|TELEGRAM_BOT_TOKEN=.*[0-9A-Za-z_-]{20}|secret-token|bot-token-secret|charge-1|invoice-1" docs/operations/production_state_checks.md docs/runbooks/telegram_sandbox_stars_smoke.md docs/analytics/events_catalog.md` -> no matches | `PASS_WITH_NOTES` | Accepted; docs-only patch, no runtime/config/migration changes. |
| P5 | 5 | Exact-match auto-recovery behind safe flags | FAIL | `010067f` | `pytest --capture=no -q tests/workers/test_telegram_stars_reconciliation_task.py tests/services/test_payment_reconciliation.py tests/economy/test_purchase_credit_service.py` -> `23 passed`; `pytest --capture=no -q tests/integration/test_purchase_premium_integration.py` -> `3 passed`; `ruff check app/db/repo/purchases_repo.py app/db/repo/entitlements_repo.py app/workers/tasks/payments_reliability_async.py tests/workers/test_telegram_stars_reconciliation_task.py` -> pass; `black --check ...` -> pass; `isort --check-only ...` -> pass; `mypy app/db/repo/purchases_repo.py app/db/repo/entitlements_repo.py app/workers/tasks/payments_reliability_async.py tests/workers/test_telegram_stars_reconciliation_task.py` -> pass | `FAIL` | Blocking issues: exactness was not revalidated inside the recovery transaction, and credited charge conflicts could be counted as success. Fixed in P5-FIX. |
| P5-FIX | 5 | Revalidate exact-match auto-recovery under lock | DONE | `16768c7` | `pytest --capture=no -q tests/workers/test_telegram_stars_reconciliation_task.py tests/services/test_payment_reconciliation.py tests/economy/test_purchase_credit_service.py` -> `25 passed`; `pytest --capture=no -q tests/integration/test_purchase_premium_integration.py` -> `3 passed`; `ruff check app/db/repo/purchases_repo.py app/db/repo/entitlements_repo.py app/workers/tasks/payments_reliability_async.py tests/workers/test_telegram_stars_reconciliation_task.py` -> pass; `black --check ...` -> pass; `isort --check-only ...` -> pass; `mypy app/db/repo/purchases_repo.py app/db/repo/entitlements_repo.py app/workers/tasks/payments_reliability_async.py tests/workers/test_telegram_stars_reconciliation_task.py` -> pass | `PASS_WITH_NOTES` | Accepted; revalidation failures preserve the original review reason, which is less precise but keeps manual review intact. |
| P6A | 6 | Store payment webhook update evidence before ACK through outbox | DONE | `3d78480` | `pytest --capture=no -q tests/api/test_telegram_webhook.py tests/workers/test_telegram_updates_task.py tests/workers/test_telegram_updates_processing_units.py tests/workers/test_telegram_updates_reliability_units.py` -> `28 passed`; `pytest --capture=no -q tests/api/test_telegram_webhook.py` -> `10 passed`; `ruff check app/api/routes/telegram_webhook.py tests/api/test_telegram_webhook.py` -> pass; `black --check app/api/routes/telegram_webhook.py tests/api/test_telegram_webhook.py` -> pass; `isort --check-only app/api/routes/telegram_webhook.py tests/api/test_telegram_webhook.py` -> pass; `mypy app/api/routes/telegram_webhook.py tests/api/test_telegram_webhook.py` -> pass | `PASS_WITH_NOTES` | Accepted; outbox evidence is interim, with best-effort dedupe and no dedicated inbox unique constraint. |
| P6B | 6 | Document payment update outbox evidence and inbox migration deferral | DONE | `0bb4160` | `rg -n "telegram_payment_update_received|payment_update_kind|payment_update_key|telegram_update_inbox|payment_events|raw_update|webhook secrets|PENDING" docs/operations/production_state_checks.md docs/runbooks/telegram_sandbox_stars_smoke.md docs/analytics/events_catalog.md` -> required entries present; `rg -n "bot[0-9]+:|TELEGRAM_BOT_TOKEN=.*[0-9A-Za-z_-]{20}|secret-token|bot-token-secret" docs/operations/production_state_checks.md docs/runbooks/telegram_sandbox_stars_smoke.md docs/analytics/events_catalog.md` -> no matches | `PASS_WITH_NOTES` | Accepted; dedicated inbox/payment_events migration and DB unique constraint remain deferred pending approval/data audit. |
| P7A | 7 | Idempotent premium entitlement and ledger credit re-entry | FAIL | `cd95bf4` | `pytest --capture=no -q tests/economy/test_purchase_entitlements_units.py tests/economy/test_purchase_credit_assets_flow_units.py tests/economy/test_purchase_credit_service.py tests/integration/test_purchase_premium_integration.py tests/integration/test_purchase_refund_integration.py` -> `21 passed`; `ruff check app/economy/purchases/service/entitlements.py app/economy/purchases/service/credit_assets.py tests/economy/test_purchase_entitlements_units.py tests/economy/test_purchase_credit_assets_flow_units.py` -> pass; `black --check ...` -> pass; `isort --check-only ...` -> pass; `mypy app/economy/purchases/service/entitlements.py app/economy/purchases/service/credit_assets.py tests/economy/test_purchase_entitlements_units.py tests/economy/test_purchase_credit_assets_flow_units.py` -> pass | `FAIL` | Blocking issue: existing purchase-ledger replay skipped duplicate ledger creation but still allowed energy/streak side effects before the guard; fixing in P7A-FIX. |
| P7A-FIX | 7 | Skip asset side effects when purchase credit ledger already exists | DONE | `c835cff` | `pytest --capture=no -q tests/economy/test_purchase_credit_assets_flow_units.py tests/economy/test_purchase_entitlements_units.py tests/economy/test_purchase_credit_service.py tests/integration/test_purchase_premium_integration.py tests/integration/test_purchase_refund_integration.py` -> `21 passed`; `ruff check app/economy/purchases/service/credit_assets.py tests/economy/test_purchase_credit_assets_flow_units.py` -> pass; `black --check ...` -> pass; `isort --check-only ...` -> pass; `mypy app/economy/purchases/service/credit_assets.py tests/economy/test_purchase_credit_assets_flow_units.py` -> pass | `PASS_WITH_NOTES` | Fixed prior P7A blocker; DB uniqueness/constraint hardening remains deferred to P7B. |
| P7B | 7 | Add read-only constraint preflight and defer unsafe migrations | FAIL | `be16109` | `pytest --capture=no -q tests/scripts/test_payment_reliability_checks.py` -> `7 passed`; `ruff check scripts/payment_reliability_checks.py tests/scripts/test_payment_reliability_checks.py` -> pass; `black --check scripts/payment_reliability_checks.py tests/scripts/test_payment_reliability_checks.py` -> pass; `isort --check-only scripts/payment_reliability_checks.py tests/scripts/test_payment_reliability_checks.py` -> pass; `mypy tests/scripts/test_payment_reliability_checks.py` -> pass; `rg -n "payments_constraint_duplicate_premium_source_purchase|payments_constraint_duplicate_purchase_credit_ledger|payments_constraint_paid_purchase_missing_charge_id|payments_constraint_paid_purchase_missing_paid_at|DB constraint hardening rule|read-only migration preflight" docs/operations/production_state_checks.md docs/runbooks/telegram_sandbox_stars_smoke.md scripts/payment_reliability_checks.py tests/scripts/test_payment_reliability_checks.py` -> required entries present | `FAIL` | Blocking issue: missing `credited_at` constraint preflight; fixing in P7B-FIX. |
| P7B-FIX | 7 | Add credited_at constraint preflight coverage | FAIL | `f6b5db0` | `pytest --capture=no -q tests/scripts/test_payment_reliability_checks.py` -> `7 passed`; `ruff check scripts/payment_reliability_checks.py tests/scripts/test_payment_reliability_checks.py` -> pass; `black --check scripts/payment_reliability_checks.py tests/scripts/test_payment_reliability_checks.py` -> pass; `isort --check-only scripts/payment_reliability_checks.py tests/scripts/test_payment_reliability_checks.py` -> pass; `mypy tests/scripts/test_payment_reliability_checks.py` -> pass; `rg -n "payments_constraint_duplicate_premium_source_purchase|payments_constraint_duplicate_purchase_credit_ledger|payments_constraint_paid_purchase_missing_charge_id|payments_constraint_paid_purchase_missing_paid_at|payments_constraint_credited_purchase_missing_credited_at|DB constraint hardening rule|read-only migration preflight" docs/operations/production_state_checks.md docs/runbooks/telegram_sandbox_stars_smoke.md scripts/payment_reliability_checks.py tests/scripts/test_payment_reliability_checks.py` -> required entries present | `FAIL` | Blocked by stop condition: `credited_at` preflight is too broad for allowed `PAID_UNCREDITED` refund path; owner decision needed before more P7B changes. |
| P7B-FIX2 | 7 | Narrow credited_at preflight for legitimate uncredited refunds | DONE | `1f0ca1d` | `.venv/bin/python -m pytest --capture=no -q tests/scripts/test_payment_reliability_checks.py` -> `11 passed in 1.90s`; `.venv/bin/python -m pytest --capture=no -q tests/economy/test_purchase_refund_state_units.py` -> `3 passed in 31.17s`; `.venv/bin/python -m pytest --capture=no -q tests/economy/test_purchase_credit_assets_flow_units.py tests/economy/test_purchase_entitlements_units.py tests/economy/test_purchase_credit_service.py tests/economy/test_purchase_refund_state_units.py tests/economy/test_purchase_refund_additional_units.py tests/economy/test_purchase_refund_errors_units.py tests/economy/test_purchase_refund_helpers_units.py` -> `31 passed in 20.62s`; `.venv/bin/python -m pytest --capture=no -q tests/services/test_payment_reconciliation.py tests/services/test_telegram_stars.py tests/workers/test_telegram_stars_reconciliation_task.py tests/workers/test_payments_reliability_async.py tests/workers/test_payments_reliability_async_credit_batch.py tests/workers/test_payments_reliability_task.py` -> `40 passed in 25.68s`; `.venv/bin/python -m pytest --capture=no -q tests/integration/test_purchase_premium_integration.py tests/integration/test_purchase_refund_integration.py tests/integration/test_payments_idempotency_purchase_flow_integration.py tests/integration/test_payments_idempotency_recovery_integration.py tests/integration/test_payments_idempotency_reconciliation_integration.py tests/integration/test_economy_invariants_b_refund_symmetry_integration.py` -> `15 passed in 42.25s`; `.venv/bin/ruff check app tests scripts` -> pass; `.venv/bin/black --check app tests scripts` -> `1341 files would be left unchanged`; `.venv/bin/isort --check-only app tests scripts` -> pass; `.venv/bin/mypy app tests` -> `Success: no issues found in 1326 source files` | `PASS_WITH_NOTES` | Accepted; uncredited `PAID_UNCREDITED -> REFUNDED` rows may keep `credited_at IS NULL`, while `CREDITED` and credited-refunded rows remain strict. |
| P8 | 8 | Payment smoke and final reliability runbook | DONE | `ff0ad91` | `rg -n "active_premium=|EntitlementsRepo\\.has_active_premium|TELEGRAM_STARS_RECONCILIATION_ENABLED=false|TELEGRAM_STARS_RECONCILIATION_DRY_RUN=true|TELEGRAM_STARS_AUTO_RECOVERY_ENABLED=false|payments_telegram_star_auto_recovered|Payment reliability rollback|credited_at IS NULL|uncredited refund" docs/runbooks/telegram_sandbox_stars_smoke.md docs/operations/production_state_checks.md docs/analytics/events_catalog.md` -> required entries present; `rg -n "bot[0-9]+:|TELEGRAM_BOT_TOKEN=.*[0-9A-Za-z_-]{20}|secret-token|bot-token-secret|charge-1|invoice-1" docs/operations/production_state_checks.md docs/runbooks/telegram_sandbox_stars_smoke.md docs/analytics/events_catalog.md` -> no matches; `git diff --check` -> pass; `git diff --name-only -- alembic deploy .github docker-compose.prod.yml '.env*'` -> no output | `PASS_WITH_NOTES` | Runbooks/docs match current implementation and safe flag defaults; no deploy, production DB write, migration, protected path, `.env*`, or secret change. |

## Baseline checks

- `git rev-parse HEAD` -> `7c0590a93c56849fae680b14508ec6531cc30f3f`.
- `.agent/project` has no `[FILL_PER_PROJECT]` placeholders.
- Code Map Agent `Ohm` independently confirmed the plan code map is current for local HEAD and
  noted that paid premium products include Week, Month, Season, and Year, so implementation must
  avoid hardcoding only Week/Month.
- Targeted baseline:
  - Command: `.venv/bin/python -m pytest --capture=no -q --ignore=tests/integration tests/api/test_telegram_webhook.py tests/bot/test_payments_handler_flow.py tests/economy/test_purchase_credit_service.py tests/services/test_payments_reliability.py tests/workers/test_payments_reliability_async.py`
  - Result: `30 passed in 14.32s`.

## Audit log

### P0 - `217bdc9` - `docs(payments): add reliability execution tracker`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Commit is docs-only and adds only this execution tracker.
- No production code, migrations, deploy config, `.env*`, secrets, Telegram runtime behavior,
  or payment/idempotency logic were changed.
- Test evidence is recorded as lead-provided; auditor did not rerun tests.
- Tracker verdict/lead response were pending during the audit and should be updated after audit
  closure.

Lead response: Accepted; tracker verdict and lead response updated after audit closure.

### P1A - `e76b1cc` - `feat(payments): add read-only reliability checks`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Patch adds a read-only checker, unit tests, and tracker metadata only.
- DB path is SELECT-only and rolls back the session.
- Webhook verification reads supplied `getWebhookInfo` JSON only; it does not call Telegram or
  require a token.
- Required payment updates include `message`, `callback_query`, and `pre_checkout_query`.
- Tests cover `allowed_updates`, read-only SQL text, and no token/secret rendering.
- Reconciliation/payment-event checks remain TODO because they depend on future phases.

Lead response: Accepted; future reconciliation/payment-event checks remain tracked for later
phases.

### P1B - `ca0fc52` - `docs(payments): require webhook payment updates checks`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Patch is scoped to docs/tracker only.
- Production checklist now requires `allowed_updates` to include `message`, `callback_query`,
  and `pre_checkout_query`, and uses the offline helper with `--skip-db --webhook-info-json`.
- Sandbox smoke binds webhook with payment-safe `allowed_updates` and verifies via
  `payment_reliability_checks`.
- Secret scan found env var placeholders and existing `.env` references only, no literal
  token/secret values.

Lead response: Accepted; docs-only patch did not change runtime behavior.

### P2A - `6b1705b` - `feat(payments): add structured successful payment logs`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Patch stays within Phase 2A scope: structured successful-payment logs plus focused tests and
  tracker metadata.
- Handler logs `payment_successful_update_received` with `invoice_payload_hash`, not raw
  `invoice_payload`.
- Service logs mark-paid and credit lifecycle events, and re-raises credit-stage exceptions to
  preserve rollback behavior.
- Tests cover no raw invoice payload in handler/service logs and credit failure logging.
- Non-blocking residual: the plan lists `update_id` as a desired log field, but the handler path
  does not receive it yet; this remains deferred to durable inbox/payment-event phases.

Lead response: Accepted; `update_id` remains tracked for later durable inbox/payment-event phases.

### P2B - `a82484d` - `feat(payments): alert on stuck payment invariants`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Patch matches Phase 2B scope: read-only invariant counts, scheduled alert task, alert routing,
  focused tests, and tracker metadata.
- Repo helpers are SELECT/count-only.
- Task alerts only for nonzero counts and payloads contain counts only, not raw payment payloads
  or secrets.
- Alert severity/routing is critical `ops_l1`, aligned with high-severity payment invariant
  intent.
- Non-blocking noise note: PagerDuty has a stable dedup key in alert payload construction, but
  Slack/generic targets can still receive repeated alerts each minute while an invariant remains
  nonzero.

Lead response: Accepted; repeated Slack/generic alerts while counts remain nonzero are tracked as
a non-blocking ops noise risk.

### P2C - `69512ad` - `feat(payments): log stale payment recovery lifecycle`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Patch stays within Phase 2C scope: structured recovery lifecycle logs and focused tests only.
- No migrations, config/deploy changes, Telegram API calls, new alerts, or recovery
  state-transition changes were introduced.
- Logs do not include `invoice_payload` or `raw_successful_payment`.
- Existing alert behavior is unchanged, and legacy `paid_uncredited_recovery_finished` log remains.
- Non-blocking noise note: `review` and `retryable_failure` outcomes now emit warning logs per
  affected purchase on each scheduled recovery pass until resolved.

Lead response: Accepted; repeated recovery warning logs while unresolved are a known non-blocking
ops noise risk.

### P2D - `2b0d7a7` - `docs(payments): document reliability alerts checks`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Patch changes only docs plus tracker metadata.
- Production docs now include read-only checker, webhook `allowed_updates`, scheduled alert task
  registration, alert event names, recovery failure scan, and escalation triggers.
- Sandbox Stars runbook adds reliability checker expectations for payment invariants and webhook
  delivery.
- Event catalog includes the Phase 2 alert names matching the plan.
- Non-blocking note: event catalog has minimal per-event payload/severity detail, but operational
  severity/escalation is covered in production checks.

Lead response: Accepted; event catalog payload/severity detail remains minimal for now because
production checks cover severity/escalation.

### P3A - `bfe751a` - `feat(payments): add Telegram Stars client`

Auditor verdict: `FAIL`

Blocking issue:

- The client built a Telegram request URL containing the bot token and re-raised
  `TelegramStarsClientError` with chained `httpx.HTTPError`. For `response.raise_for_status()`,
  the chained `HTTPStatusError` could include the full token-bearing request URL in traceback/log
  rendering.

Lead response: Fixed in P3A-FIX; HTTP status handling no longer calls `raise_for_status`, transport
errors are raised `from None`, and traceback-level tests assert token absence.

### P3A-FIX - `1e52b51` - `fix(payments): sanitize Telegram Stars client errors`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Previous token-bearing traceback failure is fixed.
- `response.raise_for_status()` is gone, `httpx.HTTPError` is re-raised `from None`, and HTTP
  status failures use a sanitized local status check.
- Traceback-format test covers the prior token-bearing URL risk.
- No scheduler, reconciliation, DB writes, migrations, config/deploy changes, or auto-credit path
  were added.

Lead response: Accepted; P3A blocker closed.

### P3B - `ee3a268` - `feat(payments): add Stars reconciliation dry-run classifier`

Auditor verdict: `FAIL`

Blocking issue:

- `WOULD_RECOVER_EXACT_MATCH` could be emitted without purchase-time/window validation. The plan
  requires charge/user/amount/time/status matching before safe recovery classification.

Lead response: Fixed in P3B-FIX; candidates now carry `created_at`, exact matches require the
transaction date to fall within a 30-minute purchase window, and same-user/same-amount candidates
outside that window classify as ambiguous instead of recoverable.

### P3B-FIX - `fef6760` - `fix(payments): require Stars reconciliation time window`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Previous exact-match time-window failure is fixed.
- Exact-match classification now requires `created_at <= transaction_date <= created_at + 30
  minutes`.
- Same-user/same-amount candidates outside the window classify as ambiguous.
- Non-blocking note: the window is fixed at 30 minutes and uses `created_at` only; later DB
  integration should preserve broader created/precheckout-time and configurable-window intent.

Lead response: Accepted; later DB integration must preserve created/precheckout-time and
configurable-window intent.

### P3C - `b1e15f3` - `feat(payments): wire disabled Stars reconciliation task`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Patch respects P3C scope: Celery wrapper and beat schedule call the Telegram Stars
  reconciliation task only.
- The async task reads settings and returns `disabled` or `dry_run_not_started` with
  `transactions_examined=0`.
- No Telegram API calls, DB/session use, writes, migrations, auto-credit path, or literal secrets
  were introduced.
- Defaults remain safe: reconciliation disabled, dry-run true, and auto-recovery disabled.
- Non-blocking note: this is wiring-only; it does not yet perform dry-run comparison,
  checkpointing, alerts, or review-record flow.

Lead response: Accepted; real dry-run comparison is tracked as P3D before Phase 4.

### P3D - `56fa4fb` - `feat(payments): run Stars reconciliation dry run`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Patch respects P3D scope: Telegram `getStarTransactions` is only reached when reconciliation is
  enabled and dry-run is true.
- Disabled and non-dry-run paths return before client construction.
- Candidate lookup is SELECT-only and bounded by charge id, invoice payload, or Telegram user/time
  window.
- The dry-run path classifies with the conservative classifier and logs/returns aggregate
  classification and severity counts only.
- No purchases, entitlements, ledger rows, review records, config, migrations, or auto-credit path
  are mutated.
- Logs do not include bot token, raw transaction payload, raw invoice payload, or raw charge id.
- Non-blocking note: persistent checkpoints/review records and dry-run alerts remain future plan
  work.

Lead response: Accepted; Phase 4 will address persistent findings/review records or documented
migration deferral.

### P4A - `e34bf1e` - `feat(payments): persist Stars reconciliation reviews`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Patch writes only `OPEN` review events to existing `outbox_events`.
- It does not add migrations or mutate purchases, entitlements, ledger rows, recovery status,
  crediting state, config, or feature flags.
- Persisted payload is minimized: reason, severity, hashed `review_key`, hashed transaction id,
  candidate purchase ids/count, and `raw_payload_stored=False`.
- No bot token, raw Telegram payload, raw invoice payload, or raw charge id is stored.
- Deduplication is stable by hashed `review_key` and `OPEN` status.
- Non-blocking note: dedupe is best-effort check-then-insert without a DB unique constraint, so it
  is not race-proof. A dedicated review table/constraint remains the stronger future path.

Lead response: Accepted; P4B will document the outbox workflow and migration-deferral limits.

### P4B - `5665a6e` - `docs(payments): document Stars reconciliation reviews`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Patch is docs/tracker only; no runtime code, config, migrations, deploy files, or feature flags
  changed.
- Production inspection SQL is read-only `SELECT` against `outbox_events` for open
  `payments_telegram_stars_reconciliation_review` rows.
- Payload minimization is documented: hashed transaction identifiers and candidate purchase ids
  only, no bot token, raw Telegram payload, raw invoice payload, or raw charge id.
- Migration deferral and dedupe limitations are explicit: best-effort outbox dedupe, no DB-level
  unique constraint until future review table/migration approval.
- Literal secret/raw-id scan over changed docs found no matches.

Lead response: Accepted; Phase 4 is closed without a new migration.

### P5 - `010067f` - `feat(payments): auto recover exact Stars payments`

Auditor verdict: `FAIL`

Blocking issues:

- Auto-recovery did not revalidate the full exact-match predicate inside the recovery transaction.
  The exact decision was made before the transaction, then the transaction only partially rechecked
  the purchase.
- A credited purchase with a conflicting `telegram_payment_charge_id` could be reported as
  `already_credited` before the charge-conflict check ran.

Lead response: Fixed in P5-FIX by re-querying candidate rows with `FOR UPDATE`, reclassifying
under lock, and adding regression tests for changed locked candidate sets and credited charge
conflicts.

### P5-FIX - `16768c7` - `fix(payments): revalidate Stars auto recovery under lock`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Previous blocker is fixed: auto-recovery re-loads candidate rows inside the recovery transaction
  with `for_update=True`, reclassifies the locked set, and refuses recovery unless the locked
  decision is exactly the same single `WOULD_RECOVER_EXACT_MATCH`.
- Credited charge-conflict risk is blocked before crediting.
- Auto-credit still only runs through `PurchaseService.apply_successful_payment` after open-review,
  status, invoice, charge, ledger, and entitlement checks.
- Defaults remain safe: reconciliation disabled, dry-run true, and auto-recovery disabled.
- No migrations, deploy/config files, or secrets changed.
- Non-blocking note: revalidation failures persist the original review decision rather than the
  locked reclassification details, so the review reason can be less precise for changed candidate
  sets.

Lead response: Accepted; manual review remains intact for revalidation failures.

### P6A - `3d78480` - `feat(payments): persist payment webhook evidence`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Payment-relevant update types are detected as `pre_checkout_query`,
  `message.successful_payment`, and `message.refunded_payment`.
- Evidence is written before enqueue using `telegram_payment_update_received`, status `PENDING`,
  and `payment_update_key`.
- Payload stores `raw_update` in DB but does not include request headers or webhook secret.
- Evidence write failure returns `503 {"status":"retry"}` before enqueue, preserving Telegram retry
  behavior.
- Generic non-payment updates bypass evidence storage and still enqueue normally.
- No migrations, config/deploy files, or `.env*` changes.
- Non-blocking notes: this is an interim outbox-based evidence store, not the dedicated
  inbox/payment_events migration described in the plan. Dedupe is best-effort through
  `payment_update_key`, without a DB unique constraint.

Lead response: Accepted; P6B will document the interim outbox evidence workflow and migration
deferral.

### P6B - `0bb4160` - `docs(payments): document payment update evidence`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Patch is docs/tracker only; no runtime code, config, migrations, deploy files, feature flags, or
  `.env*` changes.
- Docs describe the interim outbox evidence path for `telegram_payment_update_received`.
- Read-only inspection SQL is documented for evidence rows.
- Payload contract covers `payment_update_kind`, `payment_update_key`, DB-only `raw_update`, and
  supported payment update kinds.
- Docs explicitly exclude request headers/webhook secrets.
- Migration/dedupe limitations are explicit: best-effort dedupe, no DB unique constraint, and no
  dedicated replay/dead-letter state until future inbox migration approval.
- Secret scan over changed docs/tracker found no literal token-shaped secrets.

Lead response: Accepted; Phase 6 is closed with a documented migration deferral.

### P7A - `cd95bf4` - `fix(payments): make purchase crediting idempotent`

Auditor verdict: `FAIL`

Blocking issue:

- Ledger re-entry was not idempotent for side-effectful products. `credit_purchase_assets()` could
  apply paid energy and streak-saver mutations before checking whether a `PURCHASE_CREDIT` ledger
  row already existed. The existing-ledger test used an `ENERGY_10`-named product with
  `energy_credit=0`, so it did not prove side-effect replay safety.

Lead response: Fixed in P7A-FIX by checking the existing purchase credit ledger before any asset,
promo, or entitlement side effect and by adding a regression test that fails if energy, streak, promo,
or ledger creation runs on existing-ledger replay.

### P7A-FIX - `c835cff` - `fix(payments): guard purchase ledger replay side effects`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Prior P7A blocker is fixed: existing `PURCHASE_CREDIT` is checked before entitlement, paid energy,
  streak, promo, or duplicate ledger side effects.
- Regression test now uses paid energy, streak saver, and promo state, and fails if those side effects
  run on existing-ledger replay.
- Scope is limited to P7A-FIX files; no migrations, config, deploy, `.env*`, or Telegram Stars API
  behavior changed.
- Non-blocking note: DB uniqueness/constraint hardening remains deferred to P7B as planned.

Lead response: Accepted; P7B will address constraints only through read-only audit/approval-safe
documentation or explicit deferral, not unsafe migration changes.

### P7B - `be16109` - `feat(payments): add constraint preflight checks`

Auditor verdict: `FAIL`

Blocking issue:

- Constraint preflight coverage was incomplete for the plan's proposed status/payment constraints.
  The patch checked duplicate premium source purchases, duplicate purchase credit ledgers, missing
  charge id, and missing `paid_at`, but did not check missing `credited_at` for `CREDITED` or
  `REFUNDED` purchases.

Lead response: Fixed in P7B-FIX by adding `payments_constraint_credited_purchase_missing_credited_at`
to the read-only checker, docs, and unit coverage.

### P7B-FIX - `f6b5db0` - `fix(payments): cover credited-at constraint preflight`

Auditor verdict: `FAIL`

Blocking issue:

- The new `credited_at` preflight is too broad for current refund behavior. It flags every
  `REFUNDED` purchase with `credited_at IS NULL`, but refunds from `PAID_UNCREDITED` remain allowed
  and that path sets `REFUNDED` / `refunded_at` without setting `credited_at`.

Lead response: Blocked by the two-fail stop condition for the P7B constraint-preflight area. Owner
decision needed: either keep the `PAID_UNCREDITED` refund exception and narrow the preflight/future
constraint accordingly, or remove/change that refund path with matching tests before continuing.

Owner decision: `credited_at` means the user was actually credited / entitlement was actually
granted. Therefore a `PAID_UNCREDITED -> REFUNDED` purchase that was never credited may
legitimately have `credited_at IS NULL`; do not fake-fill `credited_at` and do not erase
`credited_at` after a credited purchase is later refunded.

### P7B-FIX2 - `1f0ca1d` - `fix(payments): narrow credited-at preflight`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- The preflight now allows `REFUNDED` with `credited_at IS NULL` only when there is no credit
  evidence.
- `CREDITED` rows missing `credited_at` are still flagged.
- `REFUNDED` rows with `PURCHASE_CREDIT` ledger evidence or premium entitlement evidence and
  missing `credited_at` are flagged.
- Refund code preserves the original `credited_at` by not clearing it when moving a purchase to
  `REFUNDED`; focused test coverage asserts that guarantee.
- No migrations, deploy config, protected paths, `.env*`, secrets, production deploy, or
  production DB writes were introduced.
- Safe defaults remain unchanged:
  `TELEGRAM_STARS_RECONCILIATION_ENABLED=false`,
  `TELEGRAM_STARS_RECONCILIATION_DRY_RUN=true`,
  `TELEGRAM_STARS_AUTO_RECOVERY_ENABLED=false`.
- Non-blocking note: tracker update was pending during the read-only audit and is recorded here
  after audit closure.

Lead response: Accepted; Phase 7 is unblocked and Phase 8 may proceed.

### P8 - `ff0ad91` - `docs(payments): finalize reliability runbooks`

Auditor verdict: `PASS_WITH_NOTES`

Auditor notes:

- No blocking issues.
- Phase 8 docs/tracker changes are scoped to final runbook hardening and evidence recording.
- Sandbox smoke runbook now requires purchase `paid_at` / `credited_at`, purchase credit ledger,
  premium entitlement, and app-level `EntitlementsRepo.has_active_premium(...)` proof.
- Production state checks document safe flag confirmation, auto-recovery success evidence checks,
  escalation when non-dry-run reconciliation is active without approval, and rollback steps.
- Events catalog now documents the existing `payments_telegram_star_auto_recovered` outbox event.
- No tracked diff under `alembic`, `deploy`, `.github`, `docker-compose.prod.yml`, `.env*`, or
  secret/key paths.
- Non-blocking note: this was a local read-only audit; production host history was not queried.

Lead response: Accepted; Phase 8 is complete. The payment reliability plan is PR-ready after
commit, push, and PR creation.

## Open owner decisions

- Whether to commit `PAID_UNCREDITED` before crediting in normal successful-payment flow.
- Whether durable webhook storage should cover all updates or only payment-relevant updates.
- Payment audit retention period.
- Manual compensation model and refund policy after compensation.
- Auto-recovery enablement soak gate duration.
- Telegram Stars API implementation choice if aiogram lacks typed support.
