# PR Note — 2026-02-23

## Scope
- Added hard gate tooling: `make check`, pre-commit hooks, and CI workflow.
- Formatting-only fixes required by the new gate in `app/economy/purchases/service/`.

## No Behavior Changes
- Formatting only.

## Formatting-Only Changes (Gate Compliance)
- `app/economy/purchases/service/entitlements.py`
- `app/economy/purchases/service/init.py`
- `app/economy/purchases/service/validation.py`
- `app/economy/purchases/service/credit.py`
- `app/economy/purchases/service/precheckout.py`
- `app/economy/purchases/service/__init__.py`

## Tests
- `make check` → OK
  - `ruff check app tests` → OK
  - `black --check app tests` → OK
  - `isort --check-only app tests` → OK
  - `mypy` → OK
  - `pytest -q` → 338 passed
