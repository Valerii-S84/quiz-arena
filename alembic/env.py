from __future__ import annotations

import os
from logging.config import fileConfig
from typing import TYPE_CHECKING

from sqlalchemy import MetaData, pool
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

if TYPE_CHECKING:
    from app.core.config import Settings

_TEST_MIGRATION_ENV_DEFAULTS = {
    "APP_ENV": "test",
    "TELEGRAM_BOT_TOKEN": "ci-test-token",
    "TELEGRAM_WEBHOOK_SECRET": "ci-test-secret",
    "ADMIN_PASSWORD_PLAIN": "ci-test-admin-password",
    "ADMIN_JWT_SECRET": "ci-test-admin-jwt-secret",
    "ADMIN_REFRESH_SECRET": "ci-test-admin-refresh-secret",
    "INTERNAL_API_TOKEN": "ci-test-internal-token",
    "PROMO_SECRET_PEPPER": "ci-test-promo-pepper",
    "PROMO_ENCRYPTION_KEY": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY",
    "REDIS_URL": "redis://localhost:6379/15",
    "CELERY_BROKER_URL": "redis://localhost:6379/15",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/15",
}


def _configured_database_url() -> str:
    return (os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL") or "").strip()


def _bootstrap_test_migration_env() -> str:
    database_url = _configured_database_url()
    if not database_url:
        return ""

    os.environ.setdefault("DATABASE_URL", database_url)

    database_name = (make_url(database_url).database or "").strip().lower()
    if "test" not in database_name:
        return database_url

    for key, value in _TEST_MIGRATION_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)

    return database_url


_bootstrap_test_migration_env()


def _load_settings_and_metadata() -> tuple[Settings, MetaData]:
    from app.core.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.models.base import Base

    return get_settings(), Base.metadata


config = context.config
settings, target_metadata = _load_settings_and_metadata()
config.attributes["admin_bootstrap_email"] = settings.admin_email
config.attributes["admin_bootstrap_role"] = settings.admin_role
database_url = _configured_database_url() or settings.database_url
config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def run() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

    import asyncio

    asyncio.run(run())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
