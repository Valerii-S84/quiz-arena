from __future__ import annotations

import pytest

from scripts import ensure_test_db


def test_resolve_database_url_prefers_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test"
    )
    monkeypatch.setenv(
        "TEST_DATABASE_URL", "postgresql+asyncpg://quiz:quiz@localhost:5432/other_test"
    )

    assert (
        ensure_test_db._resolve_database_url()
        == "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test"
    )


def test_resolve_database_url_falls_back_to_test_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "TEST_DATABASE_URL", "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test"
    )

    assert (
        ensure_test_db._resolve_database_url()
        == "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test"
    )


def test_resolve_database_url_requires_test_database_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="must be configured"):
        ensure_test_db._resolve_database_url()
