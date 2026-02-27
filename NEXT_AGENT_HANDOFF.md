# Next Agent Handoff (2026-02-19)

## Update (2026-02-27, Phase 2 UX + deep-link shipped; concrete remaining scope)

### What was completed in this slice
1. Private tournament bot UX baseline is now live:
   - replaced `🏆 Turnier mit Freunden (🔜 Bald verfügbar!)` with real flow
   - format select (`5/12`) + invite share (`t.me/share/url`) + copy link + start/view callbacks
2. Deep-link routing is implemented:
   - `/start tournament_<invite_code>` parses and opens tournament lobby after onboarding
3. Tournament analytics was partially closed:
   - emitted in bot flow: `private_tournament_created`, `private_tournament_joined`, `private_tournament_started`, `private_tournament_result_shared`
4. Local mandatory gate is green on this branch head:
   - `.venv/bin/ruff check .`
   - `.venv/bin/mypy .`
   - `DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test TMPDIR=/tmp .venv/bin/pytest -q`

### Exactly what remains to close Phase 2
1. Round messaging + single-message table edit (TЗ step `18`):
   - send round-start DM to each participant with opponent/deadline and `▶️ Jetzt spielen!`
   - keep one standings message per participant and update it via `edit_message_text` after each round
2. Private tournament proof cards (TЗ step `19`):
   - async-only generation (worker/background), never in handlers
   - personal card for each participant, special variant for top-3
   - upload + reuse Telegram `file_id`
3. Completion/finalization path (TЗ steps `20-21`):
   - ensure final participant-facing result screen is sent to all users after round 3
   - keep `private_tournament_result_shared` wired from final screen
   - verify `private_tournament_completed` is emitted exactly once per tournament completion path (worker-driven)
4. Final Phase 2 regression closure (TЗ step `22`):
   - add tests for round-start DM dispatch and leaderboard `edit` behavior
   - add tests for private tournament proof-card enqueue/cache reuse path
   - rerun full gate and only then start Phase 3

## Update (2026-02-27, PR #15 merged; next agent plan to close Phase 2)

### Current baseline
1. DUELL Phase 1 was merged into `origin/main` as `9998658` (`Duel (#15)`).
2. Working branch for continuation: `duel`.
3. Tournament foundation is already in place:
   - migration `M32` + DB tables (`tournaments`, `tournament_participants`, `tournament_matches`)
   - private tournament service `create/join/start`
   - Swiss pairing + lifecycle worker + tournament-match bridge to `friend_challenge`

### What next agent must implement to close Phase 2 (strict TЗ order 15-22)
1. Complete private tournament bot UX (`15`):
   - replace placeholder button `🏆 Turnier mit Freunden (🔜 Bald verfügbar!)` with real flow
   - format select (`5/12`), invite share screen, participant roster, creator `start` action
2. Deep link join routing (`15`):
   - handle `/start tournament_<invite_code>` including onboarding continuation for new users
3. Round player messaging and table updates (`18`):
   - round-start DM for each participant with opponent + deadline + `▶️ Jetzt spielen!`
   - maintain one standings message per user and update it via `edit` (not new messages)
4. Proof cards for all participants (`19`):
   - async generation only (worker/background), no render in handlers
   - top-3 special variant + regular variant for other places
   - upload and reuse Telegram `file_id`
5. Share tournament result (`20`):
   - per-user share via `t.me/share/url` from final result screen
6. Complete private tournament analytics (`21`):
   - ensure end-to-end emission:
     - `private_tournament_created`
     - `private_tournament_joined`
     - `private_tournament_started`
     - `private_tournament_completed`
     - `private_tournament_result_shared`
7. Close test gap and run full gate (`22`):
   - add/finish bot flow tests for create/join/start/table/share
   - cover round deadline technical losses + leaderboard message edit path
   - run mandatory gate:
     - `.venv/bin/ruff check .`
     - `.venv/bin/mypy .`
     - `DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test TMPDIR=/tmp .venv/bin/pytest -q`

### Phase 2 done criteria to enforce before moving to Phase 3
1. Creator can create private tournament, share invite link, start only with `>=2` participants.
2. Up to 8 users can join by deep link and see roster.
3. Swiss 3 rounds run through duel engine with 24h TTL and technical losses for no-show.
4. Standings are updated by message edit (single message per participant).
5. Every participant gets personal proof card; top-3 gets medal variant.
6. Share result works through Telegram share sheet (`t.me/share/url`).
7. Gate is fully green (`ruff`, `mypy`, `pytest`) on `.venv`.

## Update (2026-02-27, DUELL PR conflict resolved; CI green; Phase 2 remaining scope)

### Branch and CI state
1. Active working branch: `duel`.
2. Merge conflict with `main` was resolved and pushed:
   - merge commit: `ddf51cd`
3. GitHub Actions on latest `duel` head completed successfully:
   - `lint_unit`: success
   - `integration`: success

### Phase 2 already done
1. DB foundation:
   - `tournaments`, `tournament_participants`, `tournament_matches` (+ indexes/constraints)
2. Domain/repo foundation:
   - tournament repos + models
   - orchestration service `create/join/start`
   - Swiss pairing core
3. Match engine reuse:
   - `tournament_match -> friend_challenge` bridge is in place
4. Worker foundation:
   - round lifecycle worker (`registration close`, `settle`, `advance`, `complete`) exists
5. Test baseline:
   - unit/integration/worker tests for current scope are green

### Phase 2 remaining (must complete to close phase)
1. Bot UX private tournament (TЗ steps 15, 18, 20):
   - replace `🏆 Turnier mit Freunden (🔜 Bald verfügbar!)` with real flow
   - creation: format select (`5/12`)
   - share screen with `t.me/share/url`
   - creator start button enabled only with `>=2` participants
   - join view via deep link with participant roster
2. Start/deep-link routing:
   - parse and handle `/start tournament_<invite_code>`
   - preserve onboarding behavior for new users, then route into tournament join
3. Tournament chat updates (TЗ step 18):
   - one message per participant for standings
   - update leaderboard via message edit after each round (no spam)
4. Round notifications and CTA:
   - send round start DM to each participant with opponent and deadline
   - provide `▶️ Jetzt spielen!` path to duel match
5. Proof cards for private tournament (TЗ step 19):
   - async generation for all participants
   - top-3 special card variants
   - reuse/upload `file_id` cache
6. Result sharing (TЗ step 20):
   - per-user result share button via `t.me/share/url`
7. Analytics completion (TЗ step 21):
   - ensure these events are emitted end-to-end:
     - `private_tournament_created`
     - `private_tournament_joined`
     - `private_tournament_started`
     - `private_tournament_completed`
     - `private_tournament_result_shared`
8. Final test closure for phase (TЗ step 22):
   - bot flow tests for create/join/start/table/share
   - integration checks for round transitions + technical losses + leaderboard edits
   - full gate:
     - `.venv/bin/ruff check .`
     - `.venv/bin/mypy .`
     - `DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test TMPDIR=/tmp .venv/bin/pytest -q`

## Update (2026-02-27, DUELL v2 Phase 1 closed; Phase 2 planning started)

### What was changed
1. Locked active branch for DUELL+Turnier execution:
   - active branch: `duel`
2. Updated DUELL+Turnier priority doc:
   - `docs/duel_turnier_v2_priority.md`
   - Phase 1 marked as `DONE` (baseline accepted).
   - Added execution plan for Phase 2 (items 14-22 in fixed order).

### Next implementation target (immediate)
1. Start Phase 2 with migration `M32`:
   - add `tournaments`, `tournament_participants`, `tournament_matches`.
2. Build tournament orchestration layer on top of existing `friend_challenge` engine.
3. Implement private tournament bot flow + worker lifecycle + analytics + tests.

## Update (2026-02-22, P2-4 lockfile + QuizBank docs/reports completed)

### What was changed
1. Lockfile strategy and reproducibility:
   - Added pinned lockfiles:
     - `requirements.lock`
     - `requirements-dev.lock`
   - Updated dependency workflow:
     - `Dockerfile` now installs runtime deps from `requirements.lock` (wheel-based, pinned).
     - `.github/workflows/ci.yml` now:
       - verifies lockfiles are in sync with `pyproject.toml`,
       - installs from `requirements-dev.lock` + editable package (`--no-deps`).
   - Updated developer tooling/docs:
     - `Makefile` (`lock`, `lock-check` targets),
     - `README_BACKEND.md`,
     - `docs/runbooks/first_deploy_and_rollback.md`.

2. QuizBank report refresh automation and CI gate:
   - Added inventory generator:
     - `tools/quizbank_inventory_audit.py`
   - Added unified refresh/check script:
     - `scripts/quizbank_reports.py`
       - `refresh`: regenerates inventory + audit + ambiguity reports,
       - `check`: validates report freshness against `QuizBank/*.csv` and drift vs freshly generated outputs.
   - CI now enforces freshness:
     - `.github/workflows/ci.yml` step `Verify QuizBank reports freshness`.

3. Factual QuizBank docs/reports refreshed:
   - Updated docs:
     - `QuizBank/README.md` (current counts and commands),
     - `reports/quizbank_production_plan.md`.
   - Regenerated artifacts:
     - `reports/quizbank_inventory_audit.json`
     - `reports/quizbank_inventory_audit.md`
     - `reports/quizbank_audit_report.json`
     - `reports/quizbank_audit_report.md`
     - `reports/quizbank_ambiguity_scan.json`
     - `reports/quizbank_ambiguity_scan.md`
   - Old file-name drift in ambiguity report is fixed (report now reflects current bank file set).

4. Added execution report:
   - `reports/p2_4_lockfile_quizbank_docs_report_2026-02-22.md`

### Validation snapshot
1. `ruff check app tests` -> pass
2. `ruff check scripts/quizbank_reports.py tools/quizbank_inventory_audit.py` -> pass
3. `mypy app tests` -> pass
4. `TMPDIR=/tmp pytest -q --ignore=tests/integration` -> `242 passed`
5. `python scripts/quizbank_reports.py check` -> pass

## Update (2026-02-22, P2-3b edge-condition fix completed)

### Why this slice was done
- User priority changed: close `burst` + `duplicate` FAIL conditions before moving to `P2-4`.

### What was changed
1. Webhook enqueue hardening:
   - `app/api/routes/telegram_webhook.py`
   - Celery enqueue path is now timeout-bounded and offloaded from request event loop:
     - new fail-fast behavior on enqueue timeout/failure -> webhook responds `503 {"status":"retry"}` (non-2xx, so upstream retries).
   - Non-Celery test doubles are enqueued directly in-loop (prevents coroutine leak warnings in integration tests).
2. Config/env knobs:
   - `app/core/config.py`: added `TELEGRAM_WEBHOOK_ENQUEUE_TIMEOUT_MS` (default `250`).
   - `.env.example`: added `TELEGRAM_WEBHOOK_ENQUEUE_TIMEOUT_MS=250`.
   - `.env.production.example`: added `TELEGRAM_WEBHOOK_ENQUEUE_TIMEOUT_MS=250`.
3. Tests:
   - `tests/api/test_telegram_webhook.py`: added enqueue-failure and loop-bound fallback cases.
   - Revalidated smoke webhook integration path:
     - `tests/integration/test_telegram_sandbox_smoke_integration.py::test_telegram_webhook_smoke_referral_reward_choice_duplicate_replay`.

### P2-3b execution results (post-fix re-run)
Artifacts:
- `reports/k6_peak_summary_p2_3b.json`
- `reports/k6_burst_summary_p2_3b.json`
- `reports/k6_duplicate_summary_p2_3b.json`
- `reports/p2_3b_peak_gate.json`
- `reports/p2_3b_burst_gate.json`
- `reports/p2_3b_duplicate_gate_observation.json`

Outcome:
1. `peak`: PASS (`p95=5.637ms`, `error_rate=0`)
2. `burst`: PASS (`p95=5.618ms`, `error_rate=0.000195`)
3. `duplicate`: PASS (`webhook_duplicate_fail_rate=0`)

### Updated report
- `reports/p2_3_load_slo_report_2026-02-22.md` now includes a dedicated `P2-3b Re-Run After Webhook Enqueue Edge Fix` section with before/after delta.

## Update (2026-02-22, P2-3 execution completed on local dockerized k6)

### What was completed
1. Executed load profiles locally via Dockerized `grafana/k6` against local API (`127.0.0.1:8000`):
   - `steady` (`reports/k6_steady_summary.json`)
   - `peak` (`reports/k6_peak_summary.json`)
   - `burst` (`reports/k6_burst_summary.json`)
   - duplicate delivery (`reports/k6_duplicate_summary.json`)
2. Captured DB snapshots and gate artifacts:
   - `reports/p2_3_*_db_before.json`
   - `reports/p2_3_*_db_after.json`
   - `reports/p2_3_*_gate.json`
3. Updated P2-3 report with factual PASS/FAIL results:
   - `reports/p2_3_load_slo_report_2026-02-22.md`
4. Fixed SLO gate parser compatibility issue with current k6 summary format:
   - updated `scripts/evaluate_slo_gate.py` to support both legacy `values` payload and direct metric fields (`value`, `p(95)`, etc.).

### Result snapshot
1. `steady`: PASS
2. `peak`: PASS (but with generator saturation warning and dropped iterations)
3. `burst`: FAIL (high timeout/error-rate and extreme p95)
4. `duplicate`: FAIL on custom `webhook_duplicate_fail_rate` threshold (`http_req_failed` still below 1%)

### Operational note
- API process was started locally for load run (`python/uvicorn` on port `8000`); if still present in your environment, stop it before next test cycle.

## Update (2026-02-22, P2 execution handoff: P2-1 + P2-2 done, P2-3 artifacts done)

### What was completed today
1. `SLICE P2-1` implemented (retention jobs):
   - Added retention cleanup task + scheduler:
     - `app/workers/tasks/retention_cleanup.py`
   - Added retention config/env knobs:
     - `app/core/config.py`
     - `.env.example`
     - `.env.production.example`
   - Added batched delete methods:
     - `app/db/repo/processed_updates_repo.py`
     - `app/db/repo/outbox_events_repo.py`
     - `app/db/repo/analytics_repo.py`
   - Added retention indexes + migration:
     - `alembic/versions/de56fa78bc90_m21_add_retention_cleanup_indexes.py`
   - Added tests:
     - `tests/workers/test_retention_cleanup_task.py`
     - `tests/integration/test_retention_cleanup_integration.py`
   - Added hardening requested by user:
     - max runtime guard,
     - batch sleep/jitter,
     - optional Berlin-night cron scheduling (`RETENTION_CLEANUP_SCHEDULE_SECONDS=0` + hour/minute knobs).

2. `SLICE P2-2` implemented (question-selection hot path):
   - Reworked runtime selection path with cached ordered pool + deterministic circular anti-repeat pick:
     - `app/game/questions/runtime_bank.py`
   - Added stale-cache self-heal retry.
   - Added cache TTL knob:
     - `QUIZ_QUESTION_POOL_CACHE_TTL_SECONDS`.
   - Added benchmark script + report:
     - `scripts/benchmark_question_selection_hotpath.py`
     - `reports/p2_2_question_selection_hotpath_report_2026-02-22.md`
   - Synthetic benchmark result:
     - `old: 63085.87 ms`
     - `new: 13.91 ms`
     - `speedup_x: 4536.46`

3. `SLICE P2-3` artifacts implemented:
   - k6 scenarios:
     - `load/k6/webhook_start_profiles.js` (`steady/peak/burst`)
     - `load/k6/webhook_duplicate_updates.js` (duplicate-delivery pressure)
   - SLO gate tooling:
     - `scripts/pg_lock_waits_snapshot.py`
     - `scripts/evaluate_slo_gate.py`
   - SLO docs + runbook:
     - `docs/performance/p2_3_load_slo_gates.md`
   - P2-3 report scaffold:
     - `reports/p2_3_load_slo_report_2026-02-22.md`
   - Added integration test for at-least-once/idempotency under duplicate updates:
     - `tests/integration/test_telegram_updates_idempotency_integration.py`

### Commits
- `f196036` - Implement P2 retention cleanup and question-selection hot path hardening
- `9d22fd2` - Add P2-3 load profiles, SLO gates, and duplicate-update integration check

### What is still pending
1. Finish `SLICE P2-3` execution on environment with `k6` installed:
   - run `steady`, `peak`, `burst`,
   - run duplicate profile,
   - capture `reports/k6_*_summary.json`,
   - capture DB snapshots before/after runs,
   - evaluate gates via `scripts/evaluate_slo_gate.py`,
   - fill `reports/p2_3_load_slo_report_2026-02-22.md` with actual PASS/FAIL metrics.
2. Start `SLICE P2-4`:
   - add lockfile strategy for CI/prod reproducibility,
   - update QuizBank factual docs/reports,
   - add/define automation or strict manual flow for report refresh.

### Environment note
- `k6` is missing in current workspace (`k6: command not found`), so load profiles were prepared but not executed here.
- Working tree is clean after the two commits above.

## Update (2026-02-22, Critical Patch Mission: P0-2 + P1-1 Scale & DB Index Hardening)

### Why this is now top priority
- Current audit verdict: project is functionally strong but not scale-ready for 100k users.
- Two blocking areas must be closed first:
  - `P0-2`: production scaling baseline.
  - `P1-1`: missing DB indexes for hot operational/analytics queries.

### Mission objective for next agent
- Deliver a production-ready patch set that removes immediate scale blockers and hardens DB query paths.
- Keep behavior backward-compatible (no product logic rewrites in this mission).
- Final state must be deployable with zero ambiguity from runbook.

### Scope (strict)
1. Scale baseline in production compose/runtime.
2. DB index hardening via Alembic migration(s) + SQLAlchemy model parity.
3. Ops docs update for new scaling controls and rollout sequence.
4. Test coverage updates for new schema/index expectations.

### Out of scope (do not mix in this patch)
- Telegram reliability redesign (`P0-1`).
- Funnel semantics fix (`P1-2`) and health/readiness redesign (`P1-3`).
- New features, UX changes, or refactor-only changes.

### Required deliverables
1. `docker-compose.prod.yml` updated for practical scaling.
2. `.env.production.example` extended with scaling knobs.
3. `alembic/versions/<new_revision>_m17_scale_index_hardening.py` (exact name can vary, but keep milestone semantics).
4. Updated model index definitions:
   - `app/db/models/purchases.py`
   - `app/db/models/referrals.py`
   - `app/db/models/outbox_events.py`
   - `app/db/models/offers_impressions.py`
5. Runbook update:
   - `docs/runbooks/first_deploy_and_rollback.md`
6. Short execution report:
   - `reports/p0_2_p1_1_patch_report_2026-02-22.md`

### Implementation plan (must follow)

#### Phase A: Compose scale baseline (P0-2)
1. Remove hard scaling blockers in `docker-compose.prod.yml`:
   - remove `container_name` from services that must be scalable (`api`, `worker`);
   - keep static names only where scaling is not intended (`postgres`, `redis`, `caddy`, `beat`).
2. API process scaling:
   - add workers parameter to uvicorn command:
     - `--workers ${API_WORKERS:-4}`
   - keep host/port unchanged.
3. Worker throughput controls:
   - parameterize Celery worker concurrency:
     - `--concurrency=${CELERY_WORKER_CONCURRENCY:-4}`
   - keep queue list `q_high,q_normal,q_low`.
4. Add new env knobs to `.env.production.example`:
   - `API_WORKERS=4`
   - `CELERY_WORKER_CONCURRENCY=4`
5. Update runbook to reflect new scaling operations:
   - explicit `docker compose -f docker-compose.prod.yml up -d --scale api=<N> --scale worker=<M>`;
   - remove docs that depend on fixed container names for scalable services.

#### Phase B: DB index hardening (P1-1)
Create Alembic migration from current head `e1f2a3b4c5d6`.

Minimum indexes to add:
1. `purchases`:
   - partial index for recovery scans:
     - `(paid_at)` where `status='PAID_UNCREDITED' AND paid_at IS NOT NULL`
   - partial index for stale unpaid expiry:
     - `(created_at)` where `status IN ('CREATED','INVOICE_SENT') AND paid_at IS NULL`
2. `referrals`:
   - `(status, created_at)` for started/review windows.
   - `(status, qualified_at, referrer_user_id)` for reward candidate scans.
   - `(referrer_user_id, rewarded_at)` where `status='REWARDED'` for monthly cap queries.
3. `outbox_events`:
   - `(event_type, created_at DESC, id DESC)` for event feed queries.
   - `(status, created_at DESC)` for status aggregation windows.
4. `offers_impressions`:
   - `(shown_at)` for global window counters.
   - `(shown_at, offer_code)` for grouped top-offer aggregation.

Important:
- Ensure model metadata mirrors migration indexes (tests rely on schema/model consistency).
- Keep naming convention explicit and deterministic (`idx_<table>_<purpose>`).

#### Phase C: Verification and safety
Run and capture outputs in patch report:
1. `ruff check app tests`
2. `mypy app tests` (if still failing from unrelated baseline, document exact residual issue)
3. `pytest -q --ignore=tests/integration`
4. Integration DB flow:
   - ensure isolated test DB (`...quiz_arena_test`)
   - `alembic upgrade head`
   - `pytest -q -s tests/integration`
5. Migration reversibility:
   - verify `alembic downgrade -1` and `alembic upgrade head` on isolated DB.
6. Query-plan sanity for hot paths:
   - run `EXPLAIN` for representative queries from:
     - `app/db/repo/purchases_repo.py`
     - `app/db/repo/referrals_repo.py`
     - `app/db/repo/outbox_events_repo.py`
     - `app/db/repo/offers_repo.py`
   - include before/after plan summary in report.

### Acceptance criteria (Definition of Done)
- Production compose can scale `api` and `worker` without editing file each time.
- New env knobs are documented and applied in production template.
- All listed indexes exist in migration and model metadata.
- Migration is forward/backward safe on isolated test DB.
- Tests remain green (or residual failures are clearly proven unrelated).
- `reports/p0_2_p1_1_patch_report_2026-02-22.md` contains:
  - changed files list,
  - migration/index list,
  - command results,
  - risk notes and rollback instructions.

### Rollout notes for next agent
- Deploy order:
  1. ship code + migration,
  2. run migration,
  3. scale API/worker,
  4. monitor DB CPU/locks/latency.
- If migration lock risk is high on prod-sized tables, execute during low-traffic window and document fallback plan.

## Update (2026-02-20, M11-B analytics event emitters for product flows)
- Added centralized analytics event emitter utility:
  - `app/core/analytics_events.py`.
- Wired product event emission into core flows:
  - energy depletion transition -> `gameplay_energy_zero`,
  - streak rollover loss -> `streak_lost`,
  - purchase funnel transitions ->
    `purchase_init_created`,
    `purchase_invoice_sent`,
    `purchase_precheckout_ok`,
    `purchase_paid_uncredited`,
    `purchase_credited`.
- Extended daily KPI schema with purchase-funnel event counters:
  - migration: `alembic/versions/e1f2a3b4c5d6_m16_add_purchase_funnel_event_metrics.py`.
- Updated analytics pipeline and endpoint mapping to expose those counters.
- Added tests:
  - `tests/integration/test_analytics_event_emitters_integration.py`,
  - updated analytics integration tests for new funnel counters.

## Update (2026-02-20, M11-A analytics foundation)
- Added analytics data model and migration:
  - `analytics_events` table for event ingestion;
  - `analytics_daily` table for daily KPI aggregates;
  - migration: `alembic/versions/f0e1d2c3b4a5_m15_add_analytics_tables.py`.
- Added aggregation service + scheduled worker:
  - `app/services/analytics_daily.py` builds Berlin-day snapshots;
  - `app/workers/tasks/analytics_daily.py` runs hourly (`q_low`) and upserts daily rows.
- Added internal analytics KPI endpoint:
  - `GET /internal/analytics/executive` (token + IP allowlist protected).
- Wired referral reward emitted events into analytics ingestion:
  - `app/workers/tasks/referrals.py` now writes both to `outbox_events` and `analytics_events`.
- Added tests:
  - `tests/api/test_internal_analytics_auth.py`,
  - `tests/integration/test_internal_analytics_dashboard_integration.py`,
  - `tests/integration/test_analytics_daily_aggregation_integration.py`,
  - `tests/workers/test_analytics_daily_task.py`.

## Update (2026-02-20, standalone ops UI + referral notifications feed)
- Delivered standalone ops web UI (internal IP allowlist protected):
  - `GET /ops/promo`,
  - `GET /ops/referrals`,
  - `GET /ops/notifications`.
- Added internal referral notifications feed API:
  - `GET /internal/referrals/events` (filters: `window_hours`, `event_type`, `limit`).
- Wired referral reward emitted events into persistence for feed visibility:
  - worker now records `referral_reward_milestone_available` and `referral_reward_granted`
    into `outbox_events` with delivery status `SENT`/`FAILED`.
- Added tests:
  - `tests/api/test_ops_ui.py`,
  - `tests/integration/test_internal_referrals_events_integration.py`,
  - updated `tests/workers/test_referrals_task.py` and `tests/api/test_internal_referrals_auth.py`.

## Update (2026-02-20, referral reward notifications channel)
- Added external notification events for referral reward lifecycle:
  - `referral_reward_milestone_available`,
  - `referral_reward_granted`.
- Wired notification dispatch into referral reward-distribution worker:
  - `run_referral_reward_distribution_async` now emits alerts via `send_ops_alert` when milestone/reward counts are present.
- Added alert routing defaults in provider-aware alerts service:
  - both events route as `info` / `ops_l3` to `slack + generic` by default.
- Added tests:
  - `tests/workers/test_referrals_task.py` (worker notification dispatch helper),
  - `tests/services/test_alerts.py` (event routing for referral milestone notification).

## Update (2026-02-20, referral manual review workflow)
- Delivered referral triage internal APIs:
  - `GET /internal/referrals/review-queue` (window/status-filtered queue);
  - `POST /internal/referrals/{referral_id}/review` (manual decisions).
- Implemented safe decision transitions:
  - `CONFIRM_FRAUD` -> `REJECTED_FRAUD` (with enforced minimum fraud score);
  - `REOPEN` -> `STARTED` (for `REJECTED_FRAUD`/`CANCELED`);
  - `CANCEL` -> `CANCELED` (for `STARTED`/`REJECTED_FRAUD`);
  - invalid transitions return `E_REFERRAL_REVIEW_DECISION_CONFLICT`.
- Added tests:
  - `tests/api/test_internal_referrals_auth.py` (auth coverage for new endpoints),
  - `tests/integration/test_internal_referrals_review_integration.py` (queue + decision flow).
- Added ops runbook:
  - `docs/runbooks/referrals_fraud_review.md`.

## Update (2026-02-20, promo admin workflow + refund rollback automation)
- Delivered internal promo admin operations endpoints:
  - `GET /internal/promo/campaigns` (filters: `status`, `campaign_name`, `limit`);
  - `POST /internal/promo/campaigns/{promo_code_id}/status` (safe mutable transitions);
  - `POST /internal/promo/refund-rollback` (manual refund rollback, idempotent response behavior).
- Added campaign safety rules for manual unpause flow:
  - mutable transitions restricted to `ACTIVE <-> PAUSED`;
  - attempts to reactivate `DEPLETED/EXPIRED` via this endpoint return `E_PROMO_STATUS_CONFLICT`.
- Added refund-driven promo rollback automation (`PR_REVOKED` flow):
  - new periodic worker task `run_refund_promo_rollback` every 5 minutes;
  - scans refunded promo purchases and idempotently sets linked `promo_redemptions.status='REVOKED'`.
- Accounting decision implemented per spec:
  - refund rollback does not decrement `promo_codes.used_total`.
- Added tests:
  - `tests/integration/test_internal_promo_admin_integration.py`,
  - `tests/integration/test_payments_idempotency_integration.py::test_refund_promo_rollback_job_revokes_discount_redemption_without_decrementing_usage`,
  - `tests/workers/test_payments_reliability_task.py` (new wrapper coverage for rollback task).

## Update (2026-02-20, referrals dashboard + fraud triage)
- Delivered referral fraud-triage dashboard endpoint:
  - `GET /internal/referrals/dashboard`
  - internal auth parity (`X-Internal-Token` + IP allowlist).
- Dashboard output includes:
  - referral funnel/status metrics in selected time window;
  - fraud rates and rejected-fraud totals;
  - top suspicious referrers and recent fraud cases for manual triage.
- Added periodic referral fraud observability monitor:
  - `run_referrals_fraud_alerts` every 15 minutes;
  - threshold-based alert event `referral_fraud_spike_detected`.
- Added env-driven thresholds:
  - `REFERRALS_ALERT_WINDOW_HOURS`,
  - `REFERRALS_ALERT_MIN_STARTED`,
  - `REFERRALS_ALERT_MAX_FRAUD_REJECTED_RATE`,
  - `REFERRALS_ALERT_MAX_REJECTED_FRAUD_TOTAL`,
  - `REFERRALS_ALERT_MAX_REFERRER_REJECTED_FRAUD`.
- Added tests:
  - `tests/api/test_internal_referrals_auth.py`,
  - `tests/integration/test_internal_referrals_dashboard_integration.py`,
  - `tests/services/test_referrals_observability.py`,
  - `tests/workers/test_referrals_observability_task.py`.

## Update (2026-02-20, offers dashboard + thresholds)
- Delivered dedicated offers funnel dashboard endpoint:
  - `GET /internal/offers/dashboard`
  - internal auth parity (`X-Internal-Token` + IP allowlist).
- Added offers CTA attribution in purchase flow:
  - offer keyboard callbacks now include `offer` payload (`buy:<product>:offer:<impression_id>`);
  - payment handler writes `clicked_at` and `converted_purchase_id` into `offers_impressions`.
- Added periodic offers monitoring job:
  - `run_offers_funnel_alerts` every 15 minutes;
  - threshold-based ops alerts:
    - `offers_conversion_drop_detected`,
    - `offers_spam_anomaly_detected`.
- Added env-driven thresholds:
  - `OFFERS_ALERT_WINDOW_HOURS`,
  - `OFFERS_ALERT_MIN_IMPRESSIONS`,
  - `OFFERS_ALERT_MIN_CONVERSION_RATE`,
  - `OFFERS_ALERT_MAX_DISMISS_RATE`,
  - `OFFERS_ALERT_MAX_IMPRESSIONS_PER_USER`.
- Added tests:
  - `tests/api/test_internal_offers_auth.py`,
  - `tests/integration/test_internal_offers_dashboard_integration.py`,
  - `tests/bot/test_payments_handler.py`,
  - `tests/services/test_offers_observability.py`,
  - `tests/workers/test_offers_observability_task.py`.

## Update (2026-02-19, promo dashboard)
- Delivered dedicated promo observability endpoint:
  - `GET /internal/promo/dashboard`
  - internal auth parity with redeem endpoint (`X-Internal-Token` + IP allowlist).
- Dashboard output now includes:
  - promo conversion metrics (`attempts accepted/failed`, `discount reservation->applied`);
  - failure-rate breakdown by attempt result (`INVALID`, `EXPIRED`, `NOT_APPLICABLE`, `RATE_LIMITED`);
  - guard trigger indicators (`candidate abusive hashes`, `paused campaign totals/recent`).
- Added/updated tests:
  - `tests/api/test_internal_promo_auth.py` (dashboard auth coverage),
  - `tests/integration/test_internal_promo_dashboard_integration.py` (metrics correctness).
- Milestone ops note updated:
  - `docs/milestones/M10_ops.md` now records the dashboard endpoint as implemented.

## What was completed
- Friend challenge flow implemented and stabilized:
  - 12-round plan with fixed level sequence `A1x3 + A2x6 + B1x3`.
  - Both players receive the same question per round.
  - Opponent labels resolve to username/first name instead of generic `Freund`.
  - Creator can continue all rounds without waiting; round/final score updates are synced.
  - Free quota and paid ticket/premium rules wired for friend challenges.
- Friend challenge invite UX updated:
  - Share-first flow with Telegram native share URL (`Link teilen`).
  - Separate action to start duel after link sharing.
- Promo handling fixed:
  - Promo is no longer auto-captured from unrelated text by default.
  - Promo redemption runs only from explicit promo entry points.
  - Internal promo integration tests pass.
- `ARTIKEL_SPRINT` adaptive progression fixed:
  - New users start at `A1`.
  - Progress now persists across sessions/days in new table `mode_progress`.
  - Existing users without a progress row are backfilled from most recent `ARTIKEL_SPRINT` history.
  - Bounds clamped to mode range (`A1..B2`) to avoid invalid upward jumps.

## New DB migration
- Added migration:
  - `alembic/versions/d5e6f7a8b9c0_m14_add_mode_progress_table.py`
- Added migration:
  - `alembic/versions/f0e1d2c3b4a5_m15_add_analytics_tables.py`
- Added migration:
  - `alembic/versions/e1f2a3b4c5d6_m16_add_purchase_funnel_event_metrics.py`
- Current DB head verified: `e1f2a3b4c5d6`.
- Promo dashboard delivery in this update did not require DB migrations.

## Important operational notes
- Integration tests truncate core tables including:
  - `quiz_questions`
  - `promo_codes` and related promo tables
- If tests are run on shared/dev DB, re-seed after tests:
  - Re-import quiz bank.
  - Recreate required promo codes (e.g. `CHIK`) if needed.

## Validation performed
- `pytest -q -s tests/game/test_adaptive_difficulty.py tests/integration/test_artikel_sprint_progress_integration.py tests/test_data_model_metadata.py` -> passed.
- `pytest -q -s tests/integration/test_friend_challenge_integration.py::test_friend_challenge_default_uses_12_round_plan_with_level_mix_and_free_energy` -> passed.
- `ruff` checks for touched files -> passed.
- `pytest -q -s tests/api/test_internal_promo_auth.py tests/integration/test_internal_promo_dashboard_integration.py` -> passed.
- `ruff check app/api/routes/internal_promo.py app/db/repo/promo_repo.py tests/api/test_internal_promo_auth.py tests/integration/test_internal_promo_dashboard_integration.py` -> passed.

## Runtime state at handoff
- Background API and worker processes were explicitly stopped before handoff.
- Workspace prepared for clean startup by next agent.
