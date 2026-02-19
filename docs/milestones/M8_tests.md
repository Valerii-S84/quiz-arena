# M8 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_offers_triggers_integration.py` -> pass (`6 passed`).
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/bot/test_offer_keyboard.py tests/bot/test_home_keyboard.py` -> pass (`2 passed`).
- `TMPDIR=/tmp .venv/bin/python -m pytest -q` -> pass (`121 passed`).
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s tests/api/test_internal_offers_auth.py tests/integration/test_internal_offers_dashboard_integration.py tests/bot/test_offer_keyboard.py tests/bot/test_payments_handler.py tests/services/test_offers_observability.py tests/workers/test_offers_observability_task.py` -> pass (`12 passed`).

## Coverage Status
- New integration coverage for M8 includes:
  - deterministic trigger resolution (`energy_zero` beats `locked_mode_click`);
  - idempotent impression logging by `idempotency_key`;
  - anti-spam caps:
    - blocking modal cooldown (6h),
    - daily impression cap (3/day),
    - same-offer cooldown (24h),
    - mute window after `Nicht zeigen` (72h).
- New bot unit coverage includes:
  - offer keyboard CTA wiring with `offer_impression_id` in callback payload.
  - buy-callback parser coverage for plain/promo/offer payload variants.
- New observability coverage includes:
  - internal offers dashboard auth checks;
  - integration metrics validation for offers funnel dashboard;
  - threshold evaluation unit coverage;
  - worker task wrapper coverage for periodic offers monitor.

## Missing
- End-to-end Telegram sandbox scenario for offer impression -> CTA purchase -> conversion attribution.
- Load/concurrency stress test for offer evaluation queries at scale.
