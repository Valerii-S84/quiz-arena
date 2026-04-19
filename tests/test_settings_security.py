from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.test_env import DEFAULT_TEST_DATABASE_URL, resolve_test_database_url

_VALID_PROMO_ENCRYPTION_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"


def _settings_kwargs(**overrides: str) -> dict[str, str]:
    values = {
        "TELEGRAM_BOT_TOKEN": "test-bot-token",
        "TELEGRAM_WEBHOOK_SECRET": "test-webhook-secret",
        "DATABASE_URL": "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test",
        "REDIS_URL": "redis://localhost:6379/15",
        "CELERY_BROKER_URL": "redis://localhost:6379/15",
        "CELERY_RESULT_BACKEND": "redis://localhost:6379/15",
        "ADMIN_PASSWORD_PLAIN": "test-admin-password",
        "ADMIN_JWT_SECRET": "test-admin-jwt-secret",
        "ADMIN_REFRESH_SECRET": "test-admin-refresh-secret",
        "INTERNAL_API_TOKEN": "test-internal-token",
        "PROMO_SECRET_PEPPER": "test-promo-pepper",
        "PROMO_ENCRYPTION_KEY": _VALID_PROMO_ENCRYPTION_KEY,
    }
    values.update(overrides)
    return values


def test_settings_require_admin_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_JWT_SECRET", raising=False)
    kwargs = _settings_kwargs()
    kwargs.pop("ADMIN_JWT_SECRET")

    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_settings_require_admin_password_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_PLAIN", raising=False)
    kwargs = _settings_kwargs()
    kwargs.pop("ADMIN_PASSWORD_PLAIN")

    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_settings_reject_invalid_promo_encryption_key() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **_settings_kwargs(PROMO_ENCRYPTION_KEY="not-a-valid-key"),
        )


def test_get_settings_bootstraps_required_test_env_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_database_url = "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test"

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("ADMIN_JWT_SECRET", raising=False)
    monkeypatch.delenv("ADMIN_REFRESH_SECRET", raising=False)
    monkeypatch.delenv("PROMO_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    monkeypatch.delenv("PROMO_SECRET_PEPPER", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_PLAIN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()

    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.database_url == test_database_url
    assert settings.admin_jwt_secret == "ci-test-admin-jwt-secret"
    assert settings.admin_refresh_secret == "ci-test-admin-refresh-secret"
    assert settings.promo_encryption_key == _VALID_PROMO_ENCRYPTION_KEY
    assert os.environ["TEST_DATABASE_URL"] == test_database_url


def test_resolve_test_database_url_rejects_unsafe_database_url_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://quiz:quiz@db.internal:5432/quiz_arena_prod",
    )

    assert resolve_test_database_url() == DEFAULT_TEST_DATABASE_URL
