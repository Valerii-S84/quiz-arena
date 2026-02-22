# P2-4 Report: Lockfile + QuizBank Docs/Reports Refresh

Date: `2026-02-22`

## Scope
- Introduce reproducible dependency lockflow for CI/prod.
- Refresh QuizBank factual docs/reports.
- Add strict report freshness verification in CI.

## Changed Files
- `pyproject.toml`
- `requirements.lock`
- `requirements-dev.lock`
- `Dockerfile`
- `.github/workflows/ci.yml`
- `Makefile`
- `README_BACKEND.md`
- `docs/runbooks/first_deploy_and_rollback.md`
- `QuizBank/README.md`
- `scripts/quizbank_reports.py`
- `tools/quizbank_inventory_audit.py`
- `reports/quizbank_inventory_audit.json`
- `reports/quizbank_inventory_audit.md`
- `reports/quizbank_audit_report.json`
- `reports/quizbank_audit_report.md`
- `reports/quizbank_ambiguity_scan.json`
- `reports/quizbank_ambiguity_scan.md`
- `reports/quizbank_production_plan.md`

## Implementation Notes
1. Lockfile strategy (`pip-tools`):
- Added pinned `requirements.lock` (runtime/prod) and `requirements-dev.lock` (CI/dev).
- Added lock maintenance deps to dev extras (`pip-tools`, `openpyxl`, `rapidfuzz`).
- CI now verifies lockfiles are in sync with `pyproject.toml` before install.
- CI install switched to lockfiles (`pip install -r requirements-dev.lock` + `pip install --no-deps -e .`).
- Docker build switched to lock-driven wheel resolution and install from local pinned wheels.

2. QuizBank factual refresh:
- Added dedicated inventory generator: `tools/quizbank_inventory_audit.py`.
- Added unified refresh/check tool: `scripts/quizbank_reports.py`.
- Refreshed all QuizBank reports:
  - inventory,
  - full audit,
  - duplicate/ambiguity scan.
- Updated `QuizBank/README.md` and `reports/quizbank_production_plan.md` with current factual counts (`19` CSV, `5570` questions).

3. Freshness/consistency gate:
- CI step `Verify QuizBank reports freshness` runs `python scripts/quizbank_reports.py check`.
- Check enforces:
  - required report files exist,
  - report/CSV mtime drift is surfaced as notice,
  - JSON/MD reports match freshly generated outputs (timestamp fields normalized).

## Validation
- `ruff check app tests` -> `All checks passed!`
- `ruff check scripts/quizbank_reports.py tools/quizbank_inventory_audit.py` -> `All checks passed!`
- `mypy app tests` -> `Success: no issues found in 230 source files`
- `TMPDIR=/tmp pytest -q --ignore=tests/integration` -> `242 passed in 25.59s`
- `python scripts/quizbank_reports.py check` -> `QuizBank reports are up-to-date.`
- Lock regeneration check (`pip-compile --strip-extras ...` + diff against committed lockfiles) -> passed.

## Risks / Notes
- Local environment in this run does not have `make` binary; equivalent lock-check commands were executed directly.
- `scripts/quizbank_reports.py check` intentionally re-runs report generators; CI logs include generated summary output.

## Rollback
1. Revert this patch commit(s).
2. Restore previous dependency install flow in CI/Docker if needed.
3. Re-run CI to confirm baseline state.
