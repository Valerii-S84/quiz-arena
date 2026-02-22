PYTHON=.venv/bin/python
PIP=.venv/bin/pip
PIP_COMPILE=.venv/bin/pip-compile
TEST_DATABASE_URL?=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test

venv:
	python3 -m venv .venv

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.lock
	$(PIP) install --no-deps -e .

lock:
	$(PIP) install --upgrade pip pip-tools
	$(PIP_COMPILE) --strip-extras pyproject.toml --output-file requirements.lock
	$(PIP_COMPILE) --strip-extras --extra dev pyproject.toml --output-file requirements-dev.lock

lock-check:
	@TMP_REQ=$$(mktemp); TMP_DEV=$$(mktemp); \
	cp requirements.lock $$TMP_REQ; \
	cp requirements-dev.lock $$TMP_DEV; \
	$(PIP_COMPILE) --strip-extras pyproject.toml --output-file requirements.lock; \
	$(PIP_COMPILE) --strip-extras --extra dev pyproject.toml --output-file requirements-dev.lock; \
	diff -u $$TMP_REQ requirements.lock; \
	diff -u $$TMP_DEV requirements-dev.lock; \
	rm -f $$TMP_REQ $$TMP_DEV

up:
	docker compose up -d

down:
	docker compose down

run-api:
	$(PYTHON) -m app.main

run-worker:
	$(PYTHON) -m celery -A app.workers.celery_app worker -Q q_high,q_normal,q_low --loglevel=INFO

run-beat:
	$(PYTHON) -m celery -A app.workers.celery_app beat --loglevel=INFO

lint:
	.venv/bin/ruff check app tests

test:
	DATABASE_URL=$(TEST_DATABASE_URL) $(PYTHON) -m scripts.ensure_test_db
	DATABASE_URL=$(TEST_DATABASE_URL) $(PYTHON) -m alembic upgrade head
	DATABASE_URL=$(TEST_DATABASE_URL) TMPDIR=/tmp .venv/bin/pytest -q

test-integration:
	DATABASE_URL=$(TEST_DATABASE_URL) $(PYTHON) -m scripts.ensure_test_db
	DATABASE_URL=$(TEST_DATABASE_URL) $(PYTHON) -m alembic upgrade head
	DATABASE_URL=$(TEST_DATABASE_URL) TMPDIR=/tmp .venv/bin/pytest -q -s tests/integration

migrate:
	$(PYTHON) -m alembic upgrade head

import-quizbank:
	$(PYTHON) -m scripts.quizbank_import_tool --replace-all

refresh-quizbank-reports:
	$(PYTHON) scripts/quizbank_reports.py refresh

check-quizbank-reports:
	$(PYTHON) scripts/quizbank_reports.py check
