# PR Note — 2026-02-23

## Scope
- Split `app/economy/offers/service.py` into single-responsibility modules with the same API and behavior.
- Facade `app/economy/offers/service.py` preserves import path and public API.

## No Behavior Changes
- API preserved.
- Logic moved only; no functional changes.

## Tests
- `make check` → OK
  - `ruff check app tests` → OK
  - `black --check app tests` → OK
  - `isort --check-only app tests` → OK
  - `mypy` → OK
  - `pytest -q` → 338 passed

## Temporary >250 Line Exceptions
These files remain above the 250-line limit and are scheduled for follow-up splits:
- `app/api/routes/internal_referrals.py`
- `app/bot/handlers/start.py`
- `app/bot/handlers/gameplay.py`
- `app/bot/handlers/gameplay_views.py`
- `app/economy/energy/service.py`
- `app/db/repo/promo_repo.py`
- `app/db/repo/referrals_repo.py`
- `app/db/repo/analytics_repo.py`
- `app/services/alerts.py`
- `app/game/questions/runtime_bank.py`
- `app/workers/tasks/friend_challenges.py`
- `app/workers/tasks/payments_reliability.py`
- `app/workers/tasks/telegram_updates.py`

(Static assets `app/ops_ui/site/static/ops-ui.js` and `app/ops_ui/site/static/ops-ui.css` are excluded from the split plan.)
