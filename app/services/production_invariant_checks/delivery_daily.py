from __future__ import annotations

from datetime import datetime

from app.services.production_invariant_checks.types import SEVERITY_P1, InvariantCheck, build_check

_CANCEL_MESSAGE_GAP_SQL = """
    SELECT count(*)
    FROM tournament_participants p
    JOIN tournaments t ON t.id = p.tournament_id
    JOIN users u ON u.id = p.user_id
    WHERE t.type = 'DAILY_ARENA'
      AND t.status = 'CANCELED'
      AND t.registration_deadline >= :recent_cutoff
      AND u.status = 'ACTIVE'
      AND NOT EXISTS (
        SELECT 1
        FROM telegram_delivery_attempts d
        WHERE d.flow = 'daily_cup'
          AND d.task_name = 'daily_cup.cancel_delivery'
          AND d.correlation_id = ('daily_cup_cancel:' || t.id::text)
          AND d.target_type = 'daily_cup_cancel'
          AND d.target_id = t.id::text
          AND d.telegram_user_id = u.telegram_user_id
          AND d.status IN ('PENDING','SENT','FAILED','SKIPPED')
      )
"""


def build_daily_cup_delivery_checks(recent_cutoff: datetime) -> list[InvariantCheck]:
    return [
        build_check(
            name="daily_cup_cancel_message_gap",
            severity=SEVERITY_P1,
            sql=_CANCEL_MESSAGE_GAP_SQL,
            params={"recent_cutoff": recent_cutoff},
            description="Canceled Daily Cup participant is missing a durable cancel attempt.",
        )
    ]
