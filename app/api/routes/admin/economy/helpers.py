from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

STAR_TO_EUR_RATE = Decimal("0.02")


def _parse_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    parsed = datetime.fromisoformat(raw_value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
