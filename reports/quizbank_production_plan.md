# QuizBank Production Plan

## Current State

- Audit date: `2026-02-22`
- Scope: `19` CSV files in `QuizBank`
- Total rows audited: `5570`
- Result: all files are marked `ready` by automated QA

Primary source of truth for per-file metrics:
- `reports/quizbank_inventory_audit.json`
- `reports/quizbank_inventory_audit.md`
- `reports/quizbank_audit_report.json`
- `reports/quizbank_audit_report.md`
- `reports/quizbank_ambiguity_scan.json`
- `reports/quizbank_ambiguity_scan.md`

## Production Checklist

Use this checklist before every release of quiz content.

- [ ] Run `python scripts/quizbank_reports.py refresh`
- [ ] Run `python scripts/quizbank_reports.py check`
- [ ] Confirm summary has `needs_fix_count = 0`
- [ ] Confirm `critical_total = 0`
- [ ] Confirm `high_total = 0`
- [ ] Review `ready_with_cleanup_count` and resolve if non-zero
- [ ] Spot-check at least 10 random rows per changed file for linguistic quality
- [ ] Verify import in staging and run 30-question smoke session
- [ ] Freeze release candidate files and tag commit

## Quality Gates

Gate 1: Schema Integrity
- Required columns exist.
- Required fields are not empty.
- `correct_option_id` is within `0..3`.

Gate 2: Answer Integrity
- `correct_answer` matches `option_{correct_option_id+1}`.
- `correct_answer` exists among `option_1..option_4`.

Gate 3: Content Consistency
- No exact duplicate stems with different correct answers.
- No duplicate keys.
- No trailing/double spaces in content fields.

Gate 4: Operational Readiness
- `status` values are controlled (`ready` for releasable rows).
- Timestamps parse as ISO 8601 where provided.

## Phase Plan

Phase 1 (completed)
- Full audit across all files.
- Resolve W-Fragen duplicate/ambiguity issues in both XLSX and CSV versions.

Phase 2 (completed)
- Added CI gate: `python scripts/quizbank_reports.py check`.
- CI now fails on stale `quizbank_*` reports or drift against current `QuizBank/*.csv`.

Phase 3 (next)
- Add linguistic review workflow:
- assign reviewer for grammar/style on changed files
- require explicit sign-off before production publish

Phase 4 (next)
- Add content telemetry:
- track per-question wrong-answer rate in production
- auto-flag outliers for monthly review

## Notes

- `logik_luecke_sheet_template.csv` is a template file with zero content rows; keep it excluded from release import.
