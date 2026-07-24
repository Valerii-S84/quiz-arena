from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.messaging_repair_models import ExistingDeliveryOutcome, RepairTarget
from app.services.messaging_repair_targets import phase_repair_target_id


async def load_tournament_expected_targets(
    session: AsyncSession,
    *,
    flow: str,
    tournament_id: str,
) -> list[RepairTarget]:
    result = await session.execute(
        text(
            """
            SELECT
              p.user_id,
              p.standings_message_id,
              t.status,
              t.current_round
            FROM tournament_participants p
            JOIN tournaments t ON t.id = p.tournament_id
            WHERE p.tournament_id = :tournament_id
            ORDER BY p.user_id
            """
        ),
        {"tournament_id": UUID(tournament_id)},
    )
    return [
        RepairTarget(
            target_type="user",
            target_id=phase_repair_target_id(
                user_id=int(row[0]),
                standings_message_id=None if row[1] is None else int(row[1]),
                status=str(row[2]),
                current_round=int(row[3] or 0),
                flow=flow,
            ),
        )
        for row in result.all()
    ]


async def load_delivery_attempts(
    session: AsyncSession,
    *,
    flow: str,
    correlation_id: str,
) -> list[ExistingDeliveryOutcome]:
    result = await session.execute(
        text(
            """
            SELECT target_type, target_id, status, attempt_count, failure_code,
              status = 'PENDING' AND updated_at <= now() - interval '5 minutes',
              COALESCE((safe_context ->> 'pending_replay_safe')::boolean, false)
            FROM telegram_delivery_attempts
            WHERE flow = :flow
              AND correlation_id = :correlation_id
            ORDER BY target_type, target_id, id
            """
        ),
        {"flow": flow, "correlation_id": correlation_id},
    )
    return [
        ExistingDeliveryOutcome(
            target_type=str(row[0]),
            target_id=str(row[1]),
            status=str(row[2]),
            attempt_count=int(row[3] or 0),
            failure_code=None if row[4] is None else str(row[4]),
            is_stale_pending=bool(row[5]),
            pending_replay_safe=bool(row[6]),
        )
        for row in result.all()
    ]


__all__ = ["load_delivery_attempts", "load_tournament_expected_targets"]
