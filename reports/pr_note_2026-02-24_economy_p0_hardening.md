# Economy P0 Hardening (2026-02-24)

## Що було порушено
- Refund endpoint міняв тільки `purchase.status`, без симетричного `DEBIT` у ledger та без revoke entitlement/mode-access.
- Purchase credit писав кілька `PURCHASE_CREDIT` записів (energy/premium/streak/ticket), порушуючи інваріант `one purchase = one credit`.
- Promo reservation TTL був 7 днів (не 15 хв за SPEC) у двох місцях (`promo` і `purchases`).
- Premium consume робив непрямі wallet side-effects (через regen/topup в consume-flow).
- `ledger_entries` не мав append-only захисту на ORM/DB рівнях.

## Що зроблено
- Впроваджено доменний `refund_purchase(...)`:
  - lock purchase `FOR UPDATE`;
  - для `CREDITED` шукає агрегований credit і створює рівно один `PURCHASE_REFUND` (`DEBIT`) з `idempotency_key=refund:{purchase_id}`;
  - revoke `entitlements` (`ACTIVE|SCHEDULED -> REVOKED`) і `mode_access` (`ACTIVE -> REVOKED`);
  - debit wallet по `paid_energy` і `streak_saver_tokens` з metadata credit;
  - ставить `purchase.status=REFUNDED`, `refunded_at`;
  - повторний refund ідемпотентний.
- Purchase credit агреговано в один ledger entry:
  - `entry_type=PURCHASE_CREDIT`, `direction=CREDIT`, `idempotency_key=credit:purchase:{purchase_id}`;
  - деталізація перенесена в `metadata.asset_breakdown`.
- Винесено `refund` у purchase service, internal promo route залишено orchestration.
- Promo TTL приведено до 15 хв:
  - `PROMO_DISCOUNT_RESERVATION_TTL_SECONDS = 15 * 60`;
  - `PROMO_RESERVATION_TTL` синхронізовано з promo-константою.
- Premium bypass hardening:
  - при активному premium `consume_quiz` повертає success без змін `free_energy/paid_energy` і без ledger-дебіту.
- Append-only для ledger:
  - ORM guard (`before_update`/`before_delete` -> exception);
  - Alembic migration `c9d8e7f6a5b4` додає DB trigger, що блокує `UPDATE/DELETE`;
  - також оновлено `ck_ledger_entries_asset` для агрегованого `asset='PURCHASE'`.

## Інваріанти, які тепер enforced
- `one purchase = one CREDIT` у ledger (агреговано).
- `one refunded credited purchase = one DEBIT` у ledger (симетрично credit amount).
- Refund ідемпотентний (`refund:{purchase_id}`).
- Entitlements/mode access з `source_purchase_id` ревокаються при refund.
- Promo reservation TTL = 15 хв.
- Premium consume не мутує wallet.
- `ledger_entries` append-only на ORM + DB рівні.

## Додані/оновлені тести
- `tests/integration/test_purchase_credit_aggregation_integration.py`
- `tests/integration/test_purchase_refund_integration.py`
- `tests/integration/test_ledger_append_only_integration.py`
- `tests/integration/test_energy_premium_bypass_integration.py`
- оновлено:
  - `tests/integration/test_internal_promo_admin_integration.py`
  - `tests/integration/test_payments_idempotency_purchase_flow_integration.py`
  - `tests/integration/test_purchase_premium_integration.py`
  - `tests/integration/test_internal_promo_redeem_integration.py`
  - `tests/integration/test_purchase_promo_discount_integration.py`

## Gate результати
- `.venv/bin/ruff check .` -> `All checks passed!`
- `.venv/bin/mypy .` -> `Success: no issues found in 429 source files`
- `DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test TMPDIR=/tmp .venv/bin/pytest -q` -> `260 passed, 86 skipped`
- `pytest -q -s tests/integration` -> `86 skipped` (Postgres недоступний у цьому оточенні)
- `make check` -> FAIL на `black --check` через pre-existing форматування у нецільових файлах:
  - `app/db/repo/analytics_repo.py`
  - `app/db/repo/referrals_repo.py`
  - `app/economy/energy/energy_models.py`
  - `tests/game/test_runtime_bank_friend_challenge.py`
  - `app/bot/handlers/start_helpers.py`
  - `tests/integration/test_referrals_qualification_integration.py`
