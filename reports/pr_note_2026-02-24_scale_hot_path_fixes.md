# PR Note — 2026-02-24

## Scope
SLICE: Scale Hot-Path Fixes (paid_at indexes + referrals N+1 + questions pool O(N))

## Baseline Before Changes

### A) `purchases` paid_at aggregates (real SQL/WHERE)
Source: `app/db/repo/purchases_repo.py`.

- `count_paid_purchases`:
  - SQL shape: `SELECT count(purchases.id) FROM purchases WHERE purchases.paid_at IS NOT NULL`
  - WHERE: `paid_at IS NOT NULL`
- `sum_paid_stars_amount`:
  - SQL shape: `SELECT coalesce(sum(purchases.stars_amount), 0) FROM purchases WHERE purchases.paid_at IS NOT NULL`
  - WHERE: `paid_at IS NOT NULL`
- `sum_paid_stars_amount_by_product` (same paid filter):
  - SQL shape: `SELECT product_code, coalesce(sum(stars_amount), 0) FROM purchases WHERE paid_at IS NOT NULL GROUP BY product_code`
  - WHERE: `paid_at IS NOT NULL`

Observation: there is no dedicated partial index for the generic predicate `paid_at IS NOT NULL` used by these aggregate paths.

### B) Referral rewards distribution N+1 hot path
Source: `app/economy/referrals/service/rewards_distribution.py`.

Current query pattern per distribution run:
- `1` query: `list_referrer_ids_with_reward_candidates(...)`
- For each referrer `N`:
  - `1` query: `list_for_referrer_for_update(referrer_user_id=...)`
  - `1` query: `count_rewards_for_referrer_between(referrer_user_id=...)`

Baseline query-count (without grant side effects, `reward_code=None`):
- total = `1 + 2N`.
- example: for `N=50` referrers => `101` SQL statements.

N+1 location: loop over `referrer_ids` in `run_reward_distribution` does two DB round-trips per referrer.

### C) Question pool refresh O(N) place
Source: `app/game/questions/runtime_bank_pool.py`, function `_load_pool_ids(...)`.

Current refresh path executes full id list query each cache reload:
- Quick mix/all-active scope: `QuizQuestionsRepo.list_question_ids_all_active(...)`
- Mode scope: `QuizQuestionsRepo.list_question_ids_for_mode(...)`

Both repo methods run `SELECT quiz_questions.question_id ... ORDER BY quiz_questions.question_id ASC` over full active scope (no incremental watermark), i.e. full-scope reload on each refresh.

`quiz_questions.updated_at` is present in the schema and populated by import upsert (`scripts/quizbank_import_tool.py` sets and updates `updated_at`), so incremental watermark approach is viable.

## Implemented Changes

### A) paid_at indexes (Alembic)
Migration: `alembic/versions/e7f8a9b0c1d2_m25_scale_hot_path_indexes.py`.

- Added `idx_purchases_paid_at_not_null`:
  - table: `purchases`
  - key: `(paid_at)`
  - WHERE: `paid_at IS NOT NULL`
  - INCLUDE: `(stars_amount, product_code)`
- Added `idx_purchases_user_product_paid_at`:
  - table: `purchases`
  - key: `(user_id, product_code, paid_at)`
  - WHERE: `paid_at IS NOT NULL`

EXPLAIN smoke test: `tests/integration/test_purchases_paid_at_indexes_integration.py`
- Uses `EXPLAIN` (without `ANALYZE`) for:
  - `SELECT count(id) FROM purchases WHERE paid_at IS NOT NULL`
  - `SELECT COALESCE(sum(stars_amount), 0) FROM purchases WHERE paid_at IS NOT NULL`
- Asserts plan contains index scan type (`Index Scan`/`Bitmap Index Scan`/`Index Only Scan`) and index name `idx_purchases_paid_at_not_null`.

### B) Referral rewards N+1 removal

- Added batched lock query in repo:
  - `ReferralsRepo.list_for_referrers_for_update(...)`
  - single `SELECT ... WHERE referrer_user_id IN (...) ... FOR UPDATE`
- `run_reward_distribution(...)` now:
  - loads referrals for all referrers in one batch query;
  - computes `rewarded_this_month` from already loaded rows (no per-referrer count query).

Query-count guard:
- Test: `tests/integration/test_referrals_rewards_distribution_perf_integration.py`
- Invariant test covers cap/status/sum behavior.
- Guard asserts `<= 10` SQL statements for 60 referrers.
- Measured in local run: `query_count=2` (previous baseline `1 + 2N`, i.e. `101` for `N=50`).

### C) Question pool refresh incremental path

- Added incremental repo method:
  - `QuizQuestionsRepo.list_question_pool_changes_since(since_updated_at=...)`
  - SQL shape: `... WHERE updated_at > :watermark ORDER BY updated_at, question_id`.
- Runtime pool cache refresh (`app/game/questions/runtime_bank_pool.py`) now:
  - first load: full snapshot (as before);
  - subsequent stale refresh: applies incremental changes from `updated_at` watermark;
  - no full `SELECT question_id FROM quiz_questions ...` on refresh.
- Added index `idx_quiz_questions_updated_at` via Alembic for the watermark query path.

Determinism / no-full-refresh test:
- `tests/game/test_runtime_bank_cache.py::test_select_question_for_mode_refresh_uses_incremental_changes`
- Asserts refresh calls incremental changes API and does not re-run full list loader on refresh.
