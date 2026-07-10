# Звіт Payment Reliability Completion

Дата: 2026-07-09
Гілка: `feature/payment-reliability-completion`
База: `origin/main` на merge commit PR #244 `7256686`

## Обсяг

Цей звіт закриває post-merge completion gap між початковим payment reliability plan і кодом,
підготовленим для нового PR. Stale local planning artifact
`reports/payment_reliability_plan_20260707.md` не є source of truth для цього PR і не має бути
staged as-is.

## Completion matrix

| Пункт плану | Статус | Доказ | Що лишається | Migration | Ризик |
|---|---:|---|---|---:|---|
| Strict paid Stars validation | DONE | `successful_payment_validation_error`, `mark_successful_payment_paid_uncredited`, `tests/economy/test_purchase_successful_payment_validation_units.py` | Немає | Ні | Invalid paid evidence переходить у manual review і не credit-ить assets. |
| Durable `PAID_UNCREDITED` checkpoint before crediting | DONE | `app/bot/handlers/payments_runtime.py` commit-ить mark-paid перед `credit_paid_purchase`; `tests/bot/test_payments_successful_checkpoint_units.py` | Немає | Ні | Crash після paid marker лишає recoverable purchase. |
| Durable payment inbox/events before ACK | DONE | `telegram_update_inbox`, `payment_events`, `store_payment_update_evidence`, webhook tests | Немає | Так, `ac12bd34ef56_m55_payment_reliability_inbox_events.py` | Payment update ACK fail-ить, якщо durable evidence insert fail-ить. |
| Dedicated validation reviews | DONE | `payment_reconciliation_reviews`, `record_successful_payment_validation_review`, read-only checker включає dedicated rows | Немає | Так, same migration | Open validation reviews блокують automatic action до owner review. |
| Dedicated Stars reconciliation review table | NO LONGER NEEDED | Legacy Stars reconciliation review rows лишаються в `outbox_events`; read-only checker рахує їх разом із dedicated validation reviews | Тримати legacy path до окремого owner-approved migration request | Ні | Legacy review dedupe лишається best-effort; OPEN rows retained і visible. |
| Dedicated Stars checkpoint table | NO LONGER NEEDED | Stars reconciliation лишається safe/off за замовчуванням і читає bounded recent window; `PAID_UNCREDITED` є durable credit checkpoint | Owner може approve future Stars cursor, якщо live reconciliation потребуватиме цього | Ні | Live reconciliation не enabled у цьому PR. |
| Refund-only `paid_at` / `credited_at` semantics | DONE | read-only preflights і refund tests зберігають uncredited refund exception | Немає | Ні | Refund-only rows лишаються reconcilable без fake credit evidence. |
| Production enablement gates | DONE | `docs/runbooks/telegram_sandbox_stars_smoke.md`, `docs/operations/production_state_checks.md` | Sandbox smoke потребує owner-approved credentials/window | Ні | Auto-recovery і live reconciliation лишаються off за замовчуванням. |

## Підсумок gap matrix

- `DONE`: strict validation, committed paid checkpoint, durable payment inbox/events, dedicated
  validation reviews, refund-only semantics, docs/runbook gates.
- `NO LONGER NEEDED`: dedicated Stars checkpoint table для цього completion PR, бо live Stars cursor
  не enabled, а normal credit recovery використовує committed purchase checkpoint.
- `DEFERRED`: production sandbox/live smoke evidence, якщо немає sandbox credentials або approved
  smoke window.
- `NOT IMPLEMENTED`: broad all-update Telegram inbox; у scope тільки payment-relevant updates.

## Безпека production

- No deploy.
- No production DB writes.
- No `.env*`, secrets або production config changes.
- No merge to `main`.
- `TELEGRAM_STARS_RECONCILIATION_ENABLED` лишається default false.
- `TELEGRAM_STARS_RECONCILIATION_DRY_RUN` лишається default true.
- `TELEGRAM_STARS_AUTO_RECOVERY_ENABLED` лишається default false.

## Acceptance audit closeout - 2026-07-10

Acceptance audit status before this closeout: `BLOCKED`.

### Blockers

- Blocker 1: `CI=1 FORCE_GROWTH_CHECK=1 BASE_REF=origin/main bash scripts/check_line_limits.sh`
  failed on `tests/bot/test_payments_handler_flow.py` because the PR touched a 734-line test
  file.
- Blocker 2: explicit regression coverage for missing/empty
  `telegram_payment_charge_id` was absent.

### Fix

- Moved refund runtime coverage out of `tests/bot/test_payments_handler_flow.py` into
  `tests/bot/test_payments_refund_update_units.py`; coverage and assertions for charge lookup,
  invoice fallback, charge conflict, currency mismatch, and amount mismatch were preserved.
  `tests/bot/test_payments_handler_flow.py` is now 394 lines, and the new focused file is
  364 lines.
- Added `tests/integration/test_payments_missing_charge_evidence_integration.py` with real DB
  assertions for `telegram_payment_charge_id=None`, `telegram_payment_charge_id=""`, and the
  valid duplicate path. The invalid cases prove no `CREDITED` state, no active premium
  entitlement, no `PURCHASE_CREDIT`, OPEN validation review evidence, and no raw
  invoice/charge/order/email payload persistence. The valid case proves one credit, one
  `PURCHASE_CREDIT`, one entitlement, and duplicate replay without double credit.

### Local gates

- `.venv/bin/python -m pytest --capture=no -q tests/bot/test_payments_handler_flow.py tests/bot/test_payments_refund_update_units.py`
  -> `17 passed in 5.26s`.
- `.venv/bin/python -m pytest --capture=no -q tests/integration/test_payments_missing_charge_evidence_integration.py`
  -> `3 passed in 20.02s`.
- `.venv/bin/python -m pytest --capture=no -q tests/economy/test_purchase_successful_payment_validation_units.py tests/integration/test_payments_idempotency_purchase_flow_integration.py tests/integration/test_economy_invariants_a_purchase_credit_integration.py`
  -> `9 passed in 23.85s`.
- `.venv/bin/python -m pytest --capture=no -q tests/scripts/test_payment_reliability_checks.py`
  -> `20 passed in 1.55s`.
- `.venv/bin/python -m pytest --capture=no -q tests/api/test_telegram_webhook.py tests/bot/test_payments_handler_flow.py tests/bot/test_payments_handler_flow_offer.py tests/bot/test_payments_refund_mismatch_units.py tests/bot/test_payments_refund_update_units.py tests/bot/test_payments_successful_checkpoint_units.py tests/db/repo/test_payment_inbox_repo.py tests/economy/test_purchase_credit_service.py tests/economy/test_purchase_credit_service_review_units.py tests/economy/test_purchase_credit_service_zero_cost.py tests/economy/test_purchase_successful_payment_validation_units.py tests/integration/test_payments_missing_charge_evidence_integration.py tests/integration/test_payments_idempotency_purchase_flow_integration.py tests/integration/test_payments_idempotency_reconciliation_integration.py tests/integration/test_payments_idempotency_recovery_integration.py tests/integration/test_purchase_refund_integration.py tests/services/test_payment_update_evidence.py tests/services/test_payment_reconciliation.py tests/services/test_telegram_stars.py tests/workers/test_payments_reliability_async.py tests/workers/test_payments_reliability_async_credit_batch.py tests/workers/test_payments_reliability_async_credit_single.py tests/workers/test_payments_reliability_task.py tests/workers/test_telegram_stars_reconciliation_task.py`
  -> `129 passed in 57.24s`.
- `.venv/bin/ruff check app tests scripts` -> pass.
- `.venv/bin/black --check app tests scripts` -> `1361 files would be left unchanged`.
- `.venv/bin/isort --check-only app tests scripts` -> pass.
- `.venv/bin/mypy app tests` -> `Success: no issues found in 1346 source files`.
- `git diff --check` -> pass.
- `CI=1 FORCE_GROWTH_CHECK=1 BASE_REF=origin/main bash scripts/check_line_limits.sh` ->
  pass, existing soft warnings only.

### Agent statuses

- Agent B: local scope PASS for the intended acceptance-fix commit; the pre-existing untracked
  stale `reports/payment_reliability_plan_20260707.md` remains excluded from PR scope.
- Agent C: local code/test review PASS for the patch invariants; GitHub PR status remains
  blocked until this commit is pushed and CI passes.
- Agent D: local blockers/gates PASS; final `DONE_READY_TO_MERGE` requires pushed head and green
  GitHub CI.

## Sandbox-статус

`BLOCKED_FOR_SANDBOX_ACCESS`, якщо owner не надасть approved sandbox credentials і explicit smoke
window. Code completion може лишатися `DONE`, якщо local gates і review agents pass.
