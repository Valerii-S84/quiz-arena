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

## Sandbox-статус

`BLOCKED_FOR_SANDBOX_ACCESS`, якщо owner не надасть approved sandbox credentials і explicit smoke
window. Code completion може лишатися `DONE`, якщо local gates і review agents pass.
