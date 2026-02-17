PYTHON=.venv/bin/python
PIP=.venv/bin/pip

venv:
	python3 -m venv .venv

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

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
	.venv/bin/pytest -q
