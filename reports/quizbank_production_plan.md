# QuizBank Production Plan

## Current State

- Audit date: `2026-02-15`
- Scope: `21` files in `QuizBank` (`20` CSV + `1` XLSX)
- Total rows audited: `4580`
- Result: all files are marked `ready` by automated QA

Primary source of truth for per-file metrics:
- `reports/quizbank_audit_report.json`
- `reports/quizbank_audit_report.md`

## Production Checklist

Use this checklist before every release of quiz content.

- [ ] Run `python tools/quizbank_audit.py`
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

Phase 2 (next)
- Add a CI step to run `tools/quizbank_audit.py` on every PR.
- Block merge when summary has any `needs_fix_count > 0`.

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
- Keep CSV and XLSX variants synchronized when both formats exist for the same bank.
