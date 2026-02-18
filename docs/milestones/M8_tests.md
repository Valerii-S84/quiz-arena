# M8 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_offers_triggers_integration.py` -> pass (`6 passed`).
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/bot/test_offer_keyboard.py tests/bot/test_home_keyboard.py` -> pass (`2 passed`).
- `TMPDIR=/tmp .venv/bin/python -m pytest -q` -> pass (`121 passed`).

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
  - offer keyboard CTA and dismiss callback wiring.

## Missing
- End-to-end Telegram sandbox scenario for offer impression -> CTA purchase -> conversion attribution.
- Load/concurrency stress test for offer evaluation queries at scale.
