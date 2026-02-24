# CI hardening via GitHub (2026-02-24)

## Scope
- Бізнес-логіку не змінено.
- Змінені лише: `.github/workflows/ci.yml`, `.github/CODEOWNERS`, `reports/pr_note_2026-02-24_ci_hardening.md`.

## Repo changes
1. `.github/workflows/ci.yml`
- Збережено `concurrency` + `cancel-in-progress: true` (вже було).
- Додано явні job names для стабільних required checks:
  - `lint_unit`
  - `integration`

2. `.github/CODEOWNERS`
- Додано правила:
  - `/app/economy/** @OWNER`
  - `/app/db/** @OWNER`
  - `/alembic/** @OWNER`
  - `/.github/workflows/** @OWNER`
  - `/.pre-commit-config.yaml @OWNER`
- NOTE: replace `@OWNER` with real GitHub username.

## GitHub UI steps (click-by-click, needs repo admin)
1. Відкрити `GitHub -> <repo> -> Settings -> Branches`.
2. У секції `Branch protection rules` натиснути `Add rule` (або `Add branch protection rule`).
3. `Branch name pattern`: ввести `main`.
  - Якщо у репо дефолтна гілка `master`, застосувати ті самі кроки для `master` або перейменувати дефолтну гілку в `main`.
4. Увімкнути опції:
  - `Require a pull request before merging`
  - `Require approvals` = `1` (для цього slice; для командної моделі можна поставити `2`)
  - `Dismiss stale pull request approvals when new commits are pushed`
  - `Require conversation resolution before merging`
  - `Require status checks to pass before merging`
  - `Require branches to be up to date before merging`
  - `Require linear history`
  - `Do not allow bypassing the above settings`
  - `Restrict who can push to matching branches` -> дозволити тільки власника/адмінів
5. У секції required checks додати рівно:
  - `lint_unit`
  - `integration`
6. Для enforce CODEOWNERS review (потрібно для D1) у блоці PR reviews увімкнути:
  - `Require review from Code Owners`
7. Натиснути `Create` / `Save changes`.

## Required checks
- `lint_unit`
- `integration`

## Як перевірити, що merge без CI неможливий
1. Створити тестовий PR з гілки `chore/ci-hardening-smoke` у `main` (або `master`, якщо правило стоїть на `master`).
2. Дочекатися запуску CI.
3. Спробувати merge до завершення CI: кнопка merge має бути заблокована через required checks.
4. Додати новий commit у PR: попередній approve має стати stale.
5. Залишити unresolved conversation: merge має бути заблокований.
6. Зробити `main`/`master` попереду PR (new commit у base branch): merge має вимагати update branch.
7. Спробувати прямий push у захищену гілку не-адміном: push має бути відхилений.
8. Внести PR-зміну у `app/economy/` або `app/db/` або `.github/workflows/`:
  - без approve від CODEOWNER merge має бути заблокований.

## Verification checklist
- [x] Я НЕ змінював бізнес-логіку.
- [x] Я не додавав нові jobs, що збільшують час CI.
- [x] Required checks у branch protection мають збігатися 1:1 з job names у workflow (`lint_unit`, `integration`).
- [x] `CODEOWNERS` покриває економіку, БД, міграції і CI.
- [x] PR note містить click-by-click інструкцію для GitHub UI.
