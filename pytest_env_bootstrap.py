from __future__ import annotations

import importlib
import os
import sys
import tempfile

TEST_DATABASE_URL = "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test"
TEST_REDIS_URL = "redis://localhost:6379/15"
TEST_PROMO_ENCRYPTION_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"

_BOOTSTRAPPED = False


def bootstrap_pytest_env() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    resolved_test_database_url = (
        os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or TEST_DATABASE_URL
    )
    os.environ.setdefault("TEST_DATABASE_URL", resolved_test_database_url)
    os.environ.setdefault("DATABASE_URL", resolved_test_database_url)
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
