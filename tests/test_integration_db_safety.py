from __future__ import annotations

import pytest

from app.core.integration_db_safety import assert_safe_integration_db, assess_integration_db_safety


def test_assess_integration_db_safety_accepts_local_test_database() -> None:
    result = assess_integration_db_safety("postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test")

    assert result.is_safe is True
    assert result.database_name == "quiz_arena_test"
    assert result.host == "localhost"


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena",
        "postgresql+asyncpg://quiz:quiz@db.internal:5432/quiz_arena_test",
        "sqlite+aiosqlite:///tmp/quiz_arena_test.db",
    ],
)
def test_assess_integration_db_safety_rejects_unsafe_targets(database_url: str) -> None:
    result = assess_integration_db_safety(database_url)
    assert result.is_safe is False


def test_assert_safe_integration_db_raises_with_clear_message() -> None:
    with pytest.raises(RuntimeError, match="Refusing to run integration tests with destructive TRUNCATE"):
        assert_safe_integration_db("postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena")
