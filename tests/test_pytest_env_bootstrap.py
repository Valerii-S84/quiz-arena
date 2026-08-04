from __future__ import annotations

import os

import pytest

import pytest_env_bootstrap


def test_bootstrap_pytest_env_normalizes_daily_cup_flag(monkeypatch) -> None:
    monkeypatch.setenv("DAILY_CUP_ENABLED", "false")
    monkeypatch.setattr(pytest_env_bootstrap, "_BOOTSTRAPPED", False)

    pytest_env_bootstrap.bootstrap_pytest_env()

    assert os.environ["DAILY_CUP_ENABLED"] == "true"


def test_bootstrap_pytest_env_preserves_existing_database_url(
    monkeypatch,
) -> None:
    custom_database_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/quiz_arena_test"

    monkeypatch.setenv("DATABASE_URL", custom_database_url)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setattr(pytest_env_bootstrap, "_BOOTSTRAPPED", False)

    pytest_env_bootstrap.bootstrap_pytest_env()

    assert os.environ["DATABASE_URL"] == custom_database_url
    assert os.environ["TEST_DATABASE_URL"] == custom_database_url


def test_bootstrap_pytest_env_uses_test_database_url_when_database_url_missing(
    monkeypatch,
) -> None:
    custom_test_database_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/custom_test"

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("TEST_DATABASE_URL", custom_test_database_url)
    monkeypatch.setattr(pytest_env_bootstrap, "_BOOTSTRAPPED", False)

    pytest_env_bootstrap.bootstrap_pytest_env()

    assert os.environ["DATABASE_URL"] == custom_test_database_url
    assert os.environ["TEST_DATABASE_URL"] == custom_test_database_url


def test_bootstrap_pytest_env_overrides_unsafe_database_url_with_default_test_url(
    monkeypatch,
) -> None:
    unsafe_database_url = "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena"

    monkeypatch.setenv("DATABASE_URL", unsafe_database_url)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setattr(pytest_env_bootstrap, "_BOOTSTRAPPED", False)

    pytest_env_bootstrap.bootstrap_pytest_env()

    assert os.environ["DATABASE_URL"] == pytest_env_bootstrap.TEST_DATABASE_URL
    assert os.environ["TEST_DATABASE_URL"] == pytest_env_bootstrap.TEST_DATABASE_URL


def test_bootstrap_pytest_env_overrides_sync_database_url_with_default_test_url(
    monkeypatch,
) -> None:
    sync_test_database_url = "postgresql://postgres:postgres@localhost:5432/quiz_arena_test"

    monkeypatch.setenv("DATABASE_URL", sync_test_database_url)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setattr(pytest_env_bootstrap, "_BOOTSTRAPPED", False)

    pytest_env_bootstrap.bootstrap_pytest_env()

    assert os.environ["DATABASE_URL"] == pytest_env_bootstrap.TEST_DATABASE_URL
    assert os.environ["TEST_DATABASE_URL"] == pytest_env_bootstrap.TEST_DATABASE_URL


def test_bootstrap_pytest_env_rejects_sync_test_database_url_override(
    monkeypatch,
) -> None:
    sync_test_database_url = "postgresql://postgres:postgres@localhost:5432/quiz_arena_test"

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("TEST_DATABASE_URL", sync_test_database_url)
    monkeypatch.setattr(pytest_env_bootstrap, "_BOOTSTRAPPED", False)

    with pytest.raises(RuntimeError, match="TEST_DATABASE_URL must use an async PostgreSQL driver"):
        pytest_env_bootstrap.bootstrap_pytest_env()
