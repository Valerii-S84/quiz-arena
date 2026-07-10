#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from app.services.production_invariants import (
    exit_code_for,
    render_json,
    render_text,
    run_database_checks,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run read-only production critical invariants.")
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output.")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    results = await run_database_checks(datetime.now(timezone.utc))
    sys.stdout.write(render_json(results) if args.json else render_text(results))
    sys.stdout.write("\n")
    return exit_code_for(results)


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
