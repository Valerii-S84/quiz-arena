from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class PromoRedeemResult:
    redemption_id: UUID
    result_type: str
    idempotent_replay: bool
    premium_days: int | None = None
    premium_ends_at: datetime | None = None
    discount_percent: int | None = None
    reserved_until: datetime | None = None
    target_scope: str | None = None
