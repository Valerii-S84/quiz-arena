from __future__ import annotations

import argparse
import asyncio
import json
from urllib.parse import urlparse

import asyncpg  # type: ignore[import-untyped]


def _to_asyncpg_dsn(database_url: str) -> str:
    parsed = urlparse(database_url)
    if parsed.scheme in {"postgresql+asyncpg", "postgres+asyncpg"}:
        scheme = "postgresql"
    else:
        scheme = parsed.scheme
    return parsed._replace(scheme=scheme).geturl()


async def _collect(database_url: str) -> dict[str, int]:
    conn = await asyncpg.connect(_to_asyncpg_dsn(database_url))
    try:
        lock_waits = await conn.fetchval(
            """
            SELECT COUNT(*)::int
            FROM pg_stat_activity
            WHERE wait_event_type = 'Lock'
              AND state = 'active'
            """
        )
        deadlocks_total = await conn.fetchval(
            """
            SELECT COALESCE(SUM(deadlocks), 0)::bigint
            FROM pg_stat_database
            """
        )
    finally:
        await conn.close()

    return {
        "lock_waits_active": int(lock_waits or 0),
        "deadlocks_total": int(deadlocks_total or 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot current PostgreSQL lock waits/deadlocks.")
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    payload = asyncio.run(_collect(args.database_url))
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
