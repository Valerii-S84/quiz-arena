from __future__ import annotations

import asyncio
import re

import asyncpg
from sqlalchemy.engine import make_url

from app.core.config import get_settings

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_test_database_name(db_name: str) -> None:
    if "test" not in db_name.lower():
        raise RuntimeError(
            f"Refusing to create non-test database '{db_name}'. "
            "Database name must contain 'test'."
        )
    if IDENTIFIER_RE.fullmatch(db_name) is None:
        raise RuntimeError(
            f"Unsupported database name '{db_name}'. "
            "Only [A-Za-z0-9_] identifiers are supported."
        )


async def _ensure_database_exists(database_url: str) -> None:
    parsed = make_url(database_url)
    db_name = (parsed.database or "").strip()
    host = parsed.host or "localhost"
    port = int(parsed.port or 5432)
    user = parsed.username
    password = parsed.password

    if parsed.get_backend_name() != "postgresql":
        raise RuntimeError("Only PostgreSQL DATABASE_URL is supported.")
    if not db_name:
        raise RuntimeError("DATABASE_URL database name is empty.")
    if user is None:
        raise RuntimeError("DATABASE_URL username is required.")

    _validate_test_database_name(db_name)

    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database="postgres",
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if exists:
            print(f"ensure_test_db: exists db={db_name} host={host}:{port}")  # noqa: T201
            return

        await conn.execute(f'CREATE DATABASE "{db_name}"')
        print(f"ensure_test_db: created db={db_name} host={host}:{port}")  # noqa: T201
    finally:
        await conn.close()


def main() -> int:
    settings = get_settings()
    asyncio.run(_ensure_database_exists(settings.database_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
