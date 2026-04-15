from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin.overview_metrics import (
    build_kpi,
    count_first_purchase_users,
    count_purchase_users,
)
from app.api.routes.admin.overview_series import (
    count_first_quiz_users,
    count_quiz_users,
)

from .overview_payload_kpis import OverviewWindows


@dataclass(frozen=True, slots=True)
class ConversionSnapshot:
    start_users_now: int
    start_users_prev: int
    first_quiz_users_now: int
    first_quiz_users_prev: int
    quiz_users_now: int
    quiz_users_prev: int
    purchase_users_now: int
    purchase_users_prev: int
    first_purchase_users_now: int

    @property
    def start_to_quiz_now(self) -> float:
        return _safe_pct(self.first_quiz_users_now, self.start_users_now)

    @property
    def start_to_quiz_prev(self) -> float:
        return _safe_pct(self.first_quiz_users_prev, self.start_users_prev)

    @property
    def quiz_to_purchase_now(self) -> float:
        return _safe_pct(self.purchase_users_now, self.quiz_users_now)

    @property
    def quiz_to_purchase_prev(self) -> float:
        return _safe_pct(self.purchase_users_prev, self.quiz_users_prev)


def _safe_pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator * 100


async def load_conversion_snapshot(
    session: AsyncSession,
    *,
    start_users_now: int,
    start_users_prev: int,
    windows: OverviewWindows,
) -> ConversionSnapshot:
    first_quiz_users_now = await count_first_quiz_users(
        session, from_utc=windows.current_start, to_utc=windows.current_end
    )
    first_quiz_users_prev = await count_first_quiz_users(
        session, from_utc=windows.previous_start, to_utc=windows.previous_end
    )
    quiz_users_now = await count_quiz_users(
        session, from_utc=windows.current_start, to_utc=windows.current_end
    )
    quiz_users_prev = await count_quiz_users(
        session, from_utc=windows.previous_start, to_utc=windows.previous_end
    )
    purchase_users_now = await count_purchase_users(
        session, from_utc=windows.current_start, to_utc=windows.current_end
    )
    purchase_users_prev = await count_purchase_users(
        session, from_utc=windows.previous_start, to_utc=windows.previous_end
    )
    first_purchase_users_now = await count_first_purchase_users(
        session, from_utc=windows.current_start, to_utc=windows.current_end
    )
    return ConversionSnapshot(
        start_users_now=start_users_now,
        start_users_prev=start_users_prev,
        first_quiz_users_now=first_quiz_users_now,
        first_quiz_users_prev=first_quiz_users_prev,
        quiz_users_now=quiz_users_now,
        quiz_users_prev=quiz_users_prev,
        purchase_users_now=purchase_users_now,
        purchase_users_prev=purchase_users_prev,
        first_purchase_users_now=first_purchase_users_now,
    )


def build_conversion_kpis(snapshot: ConversionSnapshot) -> dict[str, dict[str, float]]:
    return {
        "start_users": build_kpi(
            current=float(snapshot.start_users_now),
            previous=float(snapshot.start_users_prev),
        ),
        "conversion_start_to_quiz": build_kpi(
            current=snapshot.start_to_quiz_now,
            previous=snapshot.start_to_quiz_prev,
        ),
        "conversion_quiz_to_purchase": build_kpi(
            current=snapshot.quiz_to_purchase_now,
            previous=snapshot.quiz_to_purchase_prev,
        ),
    }


__all__ = [
    "ConversionSnapshot",
    "build_conversion_kpis",
    "load_conversion_snapshot",
]
