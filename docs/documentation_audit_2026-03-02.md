# Documentation Audit (2026-03-02)

## Scope

Audit target:
- root `*.md`
- `docs/**`
- `PRODUCT/**`
- `QuizBank/README.md`

Goal:
- identify canonical docs,
- flag outdated docs,
- define archive/trash candidates,
- list missing docs that should be added.

## Current Source Of Truth (Keep)

These files should stay canonical:

- `README.md`
- `README_BACKEND.md`
- `AGENTS.md`
- `CODE_STYLE.md`
- `ENGINEERING_RULES.md`
- `REPO_STRUCTURE.md`
- `docs/runbooks/github_to_prod_safe_deploy.md`
- `docs/runbooks/first_deploy_and_rollback.md`
- `docs/runbooks/promo_incident_response.md`
- `docs/runbooks/referrals_fraud_review.md`
- `docs/runbooks/telegram_sandbox_stars_smoke.md`
- `docs/architecture/current_runtime_map.md`
- `docs/database/schema_quick_map.md`
- `docs/analytics/events_catalog.md`
- `docs/performance/p2_3_load_slo_gates.md`
- `docs/operations/production_state_checks.md`
- `QuizBank/README.md`

## Needs Update

1. `PRODUCT/*.md`
   - Product docs are useful but not explicitly versioned against code changes.
   - Add revision metadata (`last reviewed`, owner) to avoid drift.

## Archived (Not Canonical)

These historical files were moved to `docs/archive/` and should not be treated as runtime truth:

- `docs/archive/NEXT_AGENT_HANDOFF.md` (session/handoff log, branch-phase specific)
- `docs/archive/duel_turnier_v2_priority.md` (phase planning snapshot)
- `docs/archive/energy-system-and-monetization-strategy.md` (early strategy draft)
- `reports/*.md` (execution reports, point-in-time artifacts)

Note:
- `reports/*.md` kept in place because part of those files are generated artifacts used by current workflows.

## Removed As Trash

- `TECHNICAL_SPEC_ENERGY_STARS_BOT.md`
  - Removed as obsolete oversized specification that no longer reflects current runtime as source-of-truth.

## Missing Documentation

No critical missing docs in the current baseline set.

## Proposed Cleanup Plan

1. Keep `architecture/database/analytics/operations` docs updated on each schema/runtime change.
2. Add a lightweight doc policy section in `README.md`:
   - canonical vs archive docs,
   - update owner,
   - review cadence.
