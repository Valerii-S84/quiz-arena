# AGENTS.md

## Призначення
Цей файл — короткі правила для будь‑якого агента, який працює в репозиторії.

## Обов'язково дотримуватись
- `CODE_STYLE.md` (стиль, ліміти розміру файлів, заборони).
- `ENGINEERING_RULES.md` (pre-commit gate: black/isort/ruff/mypy/pytest).
- `README_BACKEND.md` (setup, запуск, тестовий gate).
- `REPO_STRUCTURE.md` (архітектурні правила та імпорти).

## Gate (перед відповіддю)
- Використовуй **тільки** venv:
  - `.venv/bin/ruff check app tests`
  - `.venv/bin/black --check app tests`
  - `.venv/bin/isort --check-only app tests`
  - `.venv/bin/mypy app tests`
  - `DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test TMPDIR=/tmp .venv/bin/pytest -q --ignore=tests/integration`
  - Для повного локального повторення всього GitHub CI: `bash scripts/local_ci.sh`
- Не запускати голі `black/isort/ruff/mypy/pytest` без `.venv/bin/...`.

## Архітектура (інваріанти)
- Bot‑шар тільки orchestration, **без** бізнес‑логіки.
- Заборонено `print(` в `app/`.
- Заборонено `except Exception: pass` у всьому репо.
- Заборонено імпорти `domains -> app.bot`.

## Split‑only правила
- **0 змін поведінки**.
- Зберегти старі import path через фасад.
- Нові файли менші за ліміти (див. `CODE_STYLE.md`).
- Коміт: `refactor(<area>): ... (no behavior changes)`.

## Комунікація
- З користувачем — українською.
- Якщо є конфлікт інструкцій, уточнюй пріоритет у користувача.
