from __future__ import annotations

import os
import shlex
import sys

from app.core.integration_db_safety import assess_integration_db_safety

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://quiz:quiz@127.0.0.1:5432/quiz_arena_test"
DEFAULT_TEST_REDIS_URL = "redis://127.0.0.1:6379/0"
DEFAULT_TEST_CELERY_BROKER_URL = "redis://127.0.0.1:6379/1"
DEFAULT_TEST_CELERY_RESULT_BACKEND = "redis://127.0.0.1:6379/2"
DEFAULT_TEST_PROMO_ENCRYPTION_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"
DEFAULT_TEST_TMPDIR = "/tmp"

_STATIC_TEST_ENV_DEFAULTS = {
    "APP_ENV": "test",
    "LOG_LEVEL": "INFO",
    "TELEGRAM_BOT_TOKEN": "ci-test-token",
    "TELEGRAM_WEBHOOK_SECRET": "ci-test-secret",
    "ADMIN_PASSWORD_PLAIN": "ci-test-admin-password",
    "ADMIN_JWT_SECRET": "ci-test-admin-jwt-secret",
    "ADMIN_REFRESH_SECRET": "ci-test-admin-refresh-secret",
    "INTERNAL_API_TOKEN": "ci-internal-token",
    "PROMO_SECRET_PEPPER": "ci-test-promo-pepper",
    "PROMO_ENCRYPTION_KEY": DEFAULT_TEST_PROMO_ENCRYPTION_KEY,
}


def _read_env(name: str) -> str:
    return os.environ.get(name, "").strip()


def is_test_env_enabled() -> bool:
    return _read_env("APP_ENV").lower() == "test"


def _safe_database_url_fallback() -> str:
    database_url = _read_env("DATABASE_URL")
    if not database_url:
        return ""
    if not assess_integration_db_safety(database_url).is_safe:
        return ""
    return database_url


def resolve_test_database_url() -> str:
    return (
        _read_env("TEST_DATABASE_URL") or _safe_database_url_fallback() or DEFAULT_TEST_DATABASE_URL
    )


def build_test_env_defaults() -> dict[str, str]:
    database_url = resolve_test_database_url()
    redis_url = _read_env("REDIS_URL") or DEFAULT_TEST_REDIS_URL
    return {
        **_STATIC_TEST_ENV_DEFAULTS,
        "TEST_DATABASE_URL": database_url,
        "DATABASE_URL": database_url,
        "REDIS_URL": redis_url,
        "CELERY_BROKER_URL": _read_env("CELERY_BROKER_URL") or DEFAULT_TEST_CELERY_BROKER_URL,
        "CELERY_RESULT_BACKEND": _read_env("CELERY_RESULT_BACKEND")
        or DEFAULT_TEST_CELERY_RESULT_BACKEND,
        "TMPDIR": _read_env("TMPDIR") or DEFAULT_TEST_TMPDIR,
    }


def apply_test_env_defaults(*, force_database_url_to_test: bool = False) -> dict[str, str]:
    defaults = build_test_env_defaults()
    for env_name, env_value in defaults.items():
        if env_name == "DATABASE_URL":
            if force_database_url_to_test or not _read_env(env_name):
                os.environ[env_name] = env_value
            continue
        if not _read_env(env_name):
            os.environ[env_name] = env_value
    return defaults


def apply_test_env_defaults_if_requested(
    *, force_database_url_to_test: bool = False
) -> dict[str, str]:
    if not is_test_env_enabled():
        return {}
    return apply_test_env_defaults(force_database_url_to_test=force_database_url_to_test)


def render_shell_exports() -> str:
    exports = [
        f"export {env_name}={shlex.quote(env_value)}"
        for env_name, env_value in build_test_env_defaults().items()
    ]
    return "\n".join(exports)


def main() -> int:
    sys.stdout.write(f"{render_shell_exports()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
