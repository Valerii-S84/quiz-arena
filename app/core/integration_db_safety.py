from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.engine import make_url

TEST_DB_NAME_RE = re.compile(r"test", re.IGNORECASE)
ALLOWED_LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "postgres",
    "quiz_arena_postgres",
    "quiz_arena_postgres_prod",
}


@dataclass(frozen=True, slots=True)
class IntegrationDbSafetyResult:
    is_safe: bool
    reason: str
    database_name: str
    host: str


def assess_integration_db_safety(database_url: str) -> IntegrationDbSafetyResult:
    parsed = make_url(database_url)
    db_name = (parsed.database or "").strip()
    host = (parsed.host or "").strip().lower()

    if parsed.get_backend_name() != "postgresql":
        return IntegrationDbSafetyResult(
            is_safe=False,
            reason="Integration tests support only PostgreSQL test databases.",
            database_name=db_name,
            host=host,
        )

    if not db_name:
        return IntegrationDbSafetyResult(
            is_safe=False,
            reason="Database name is empty.",
            database_name=db_name,
            host=host,
        )

    if TEST_DB_NAME_RE.search(db_name) is None:
        return IntegrationDbSafetyResult(
            is_safe=False,
            reason="Database name must clearly indicate a test database (contain 'test').",
            database_name=db_name,
            host=host,
        )

    if host not in ALLOWED_LOCAL_HOSTS:
        return IntegrationDbSafetyResult(
            is_safe=False,
            reason="Host is not in allowed local integration-test hosts.",
            database_name=db_name,
            host=host,
        )

    return IntegrationDbSafetyResult(
        is_safe=True,
        reason="ok",
        database_name=db_name,
        host=host,
    )


def assert_safe_integration_db(database_url: str) -> None:
    result = assess_integration_db_safety(database_url)
    if result.is_safe:
        return

    raise RuntimeError(
        "Refusing to run integration tests with destructive TRUNCATE.\n"
        f"Reason: {result.reason}\n"
        f"Resolved DB: name='{result.database_name}' host='{result.host}'\n"
        "Required: use a dedicated local PostgreSQL test DB, e.g. 'quiz_arena_test'."
    )
