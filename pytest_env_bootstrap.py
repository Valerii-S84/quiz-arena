from __future__ import annotations

import importlib
import os
import sys
import tempfile

from sqlalchemy.engine import make_url

from app.core.integration_db_safety import assert_safe_integration_db, assess_integration_db_safety

TEST_DATABASE_URL = "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test"
TEST_REDIS_URL = "redis://localhost:6379/15"
TEST_PROMO_ENCRYPTION_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"

_BOOTSTRAPPED = False


def _uses_async_database_driver(database_url: str) -> bool:
    return make_url(database_url).drivername == "postgresql+asyncpg"


def _resolve_test_database_url() -> str:
    explicit_test_database_url = os.environ.get("TEST_DATABASE_URL")
    if explicit_test_database_url:
        assert_safe_integration_db(explicit_test_database_url)
        if not _uses_async_database_driver(explicit_test_database_url):
            raise RuntimeError(
                "TEST_DATABASE_URL must use an async PostgreSQL driver compatible with "
                "create_async_engine."
            )
        return explicit_test_database_url

    existing_database_url = os.environ.get("DATABASE_URL")
    if (
        existing_database_url
        and assess_integration_db_safety(existing_database_url).is_safe
        and _uses_async_database_driver(existing_database_url)
    ):
        return existing_database_url

    return TEST_DATABASE_URL


def bootstrap_pytest_env() -> None:
    global _BOOTSTRAPPED
    os.environ["DAILY_CUP_ENABLED"] = "true"
    if _BOOTSTRAPPED:
        return

    resolved_test_database_url = _resolve_test_database_url()
    os.environ["TEST_DATABASE_URL"] = resolved_test_database_url
    os.environ["DATABASE_URL"] = resolved_test_database_url
    os.environ.setdefault("TMPDIR", tempfile.gettempdir())
    os.environ.setdefault("REDIS_URL", TEST_REDIS_URL)
    os.environ.setdefault("CELERY_BROKER_URL", TEST_REDIS_URL)
    os.environ.setdefault("CELERY_RESULT_BACKEND", TEST_REDIS_URL)
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("ADMIN_PASSWORD_PLAIN", "ci-test-admin-password")
    os.environ.setdefault("ADMIN_JWT_SECRET", "ci-test-admin-jwt-secret")
    os.environ.setdefault("ADMIN_REFRESH_SECRET", "ci-test-admin-refresh-secret")
    os.environ.setdefault("INTERNAL_API_TOKEN", "ci-test-internal-token")
    os.environ.setdefault("PROMO_SECRET_PEPPER", "ci-test-promo-pepper")
    os.environ.setdefault("PROMO_ENCRYPTION_KEY", TEST_PROMO_ENCRYPTION_KEY)

    if "app.core.config" in sys.modules:
        config_module = sys.modules["app.core.config"]
        get_settings = getattr(config_module, "get_settings", None)
        if callable(get_settings):
            get_settings.cache_clear()
            setattr(config_module, "settings", get_settings())

    if "app.db.session" in sys.modules:
        importlib.reload(sys.modules["app.db.session"])

    _BOOTSTRAPPED = True
