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

## Regression test pack
- `tests/integration/test_economy_invariants_a_purchase_credit_integration.py::test_credit_creates_single_ledger_entry_per_purchase`
- `tests/integration/test_economy_invariants_a_purchase_credit_integration.py::test_credit_is_idempotent_on_same_purchase`
- `tests/integration/test_economy_invariants_a_purchase_credit_integration.py::test_credit_contains_expected_breakdown_keys_for_friend_challenge_ticket`
- `tests/integration/test_economy_invariants_a_purchase_credit_integration.py::test_credit_mutates_wallet_only_by_expected_breakdown_delta`
- `tests/integration/test_economy_invariants_b_refund_symmetry_integration.py::test_refund_creates_single_debit_and_marks_refunded`
- `tests/integration/test_economy_invariants_b_refund_symmetry_integration.py::test_refund_is_idempotent_without_duplicate_debits`
- `tests/integration/test_economy_invariants_b_refund_symmetry_integration.py::test_refund_revokes_entitlements_for_source_purchase`
- `tests/integration/test_economy_invariants_b_refund_symmetry_integration.py::test_refund_revokes_mode_access_for_source_purchase`
- `tests/integration/test_economy_invariants_b_refund_symmetry_integration.py::test_refund_requires_credited_purchase`
- `tests/integration/test_economy_invariants_b_refund_symmetry_integration.py::test_refund_after_recovery_keeps_single_credit_and_single_debit`
- `tests/integration/test_economy_invariants_c_premium_bypass_integration.py::test_premium_bypass_does_not_change_free_or_paid_energy`
- `tests/integration/test_economy_invariants_c_premium_bypass_integration.py::test_non_premium_consume_decrements_paid_bucket_when_free_empty`
- `tests/integration/test_economy_invariants_d_promo_ttl_integration.py::test_promo_reservation_ttl_is_15_minutes`
- `tests/integration/test_economy_invariants_d_promo_ttl_integration.py::test_promo_reservation_expiry_blocks_precheckout_validation`
- `tests/integration/test_economy_invariants_e_ledger_append_only_integration.py::test_ledger_update_fails_on_db_trigger`
- `tests/integration/test_economy_invariants_e_ledger_append_only_integration.py::test_ledger_delete_fails_on_db_trigger`

## Gate результати
- `docker compose up -d postgres redis` -> containers `quiz_arena_postgres` (healthy) і `quiz_arena_redis` (up)
- `DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test .venv/bin/python -m scripts.ensure_test_db` -> `ensure_test_db: exists db=quiz_arena_test host=localhost:5432`
- `DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test .venv/bin/python -m alembic upgrade head` -> upgraded to `c9d8e7f6a5b4`
- `.venv/bin/ruff check .` -> `All checks passed!`
- `.venv/bin/mypy .` -> `Success: no issues found in 429 source files`
- `make check` -> `346 passed in 90.75s`
- `TMPDIR=/tmp .venv/bin/pytest -q --ignore=tests/integration` -> `260 passed in 28.95s`
- `DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test TMPDIR=/tmp .venv/bin/pytest -q -s tests/integration` -> `86 passed in 87.88s`
