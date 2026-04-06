from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

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
        Settings(_env_file=None, **kwargs)


def test_settings_require_admin_password_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_PLAIN", raising=False)
    kwargs = _settings_kwargs()
    kwargs.pop("ADMIN_PASSWORD_PLAIN")

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **kwargs)


def test_settings_reject_invalid_promo_encryption_key() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            **_settings_kwargs(PROMO_ENCRYPTION_KEY="not-a-valid-key"),
        )
