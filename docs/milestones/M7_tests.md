# M7 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_purchase_premium_integration.py` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q` -> pass.

## Coverage Status
- Integration tests cover:
  - first premium purchase grants active entitlement;
  - upgrade extends from existing premium end and revokes old entitlement;
  - downgrade during active higher tier is blocked.
- Purchase and payment idempotency suites remain green with premium slice enabled.

## Missing
- High-concurrency premium purchase race tests (same user, parallel premium upgrades).
- Dedicated end-to-end Telegram sandbox validation for premium payment callbacks.
