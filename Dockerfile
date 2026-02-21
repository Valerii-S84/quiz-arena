FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README_BACKEND.md ./
COPY app ./app

RUN python -m pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels .


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY --from=builder /wheels /wheels
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir --no-index --find-links=/wheels quiz-arena-bot \
    && rm -rf /wheels

COPY --chown=app:app app/ops_ui/site /usr/local/lib/python3.12/site-packages/app/ops_ui/site
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app QuizBank ./QuizBank

RUN ln -sf /tmp/celerybeat-schedule /app/celerybeat-schedule

USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
