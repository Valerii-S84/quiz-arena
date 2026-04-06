# CHANGELOG

## 1.0.1 - 2026-04-06

- Added explicit `version:` frontmatter to `.agent/AGENTS.md`
  for checklist compatibility.
- Synced `bundle_version` to `1.0.1` without changing bundle
  rules.

## 1.0.0 - 2026-04-05

- Introduced the portable `.agent/` structure with `core/` and
  `project/`.
- Moved `WORK_SCOPE.md`, `DEFINITION_OF_DONE.md`,
  `TASK_OUTPUT_FORMAT.md`, and `AUTO_CHECKLIST.md` into
  `.agent/core/` without content changes.
- Replaced the legacy flat `SECURITY_RULES.md` with a universal
  `Always / Ask First / Never` matrix in `.agent/core/`.
- Split the legacy `CODE_STYLE.md` into
  `.agent/core/PRINCIPLES.md` and `.agent/project/CODE_STYLE.md`.
- Added `.agent/core/GIT_WORKFLOW.md` and onboarding guidance in
  `.agent/AGENTS.md`.
