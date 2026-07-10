from __future__ import annotations

from datetime import datetime

from app.services.production_invariant_checks.types import SEVERITY_P1, InvariantCheck, build_check


def build_daily_cup_delivery_checks(recent_cutoff: datetime) -> list[InvariantCheck]:
    return [
        build_check(
            name="daily_cup_expected_delivery_zero_outcomes",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM tournaments t
                WHERE t.type = 'DAILY_ARENA'
                  AND t.status IN ('ROUND_1','ROUND_2','ROUND_3','ROUND_4','COMPLETED')
                  AND t.created_at >= :recent_cutoff
                  AND EXISTS (
                    SELECT 1
                    FROM tournament_participants p
                    JOIN users u ON u.id = p.user_id
                    WHERE p.tournament_id = t.id
                      AND u.status = 'ACTIVE'
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM telegram_delivery_attempts d
                    WHERE d.flow IN (
                      'daily_cup_round_messaging',
                      'daily_cup_cancel_message',
                      'daily_cup_turn_reminder'
                    )
                      AND d.correlation_id = t.id::text
                      AND d.status IN ('SENT','FAILED','SKIPPED')
                  )
            """,
            params={"recent_cutoff": recent_cutoff},
            description="Recent Daily Cup expected messaging has zero durable outcomes.",
        ),
        build_check(
            name="daily_cup_round_delivery_gap",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM tournament_participants p
                JOIN tournaments t ON t.id = p.tournament_id
                JOIN users u ON u.id = p.user_id
                WHERE t.type = 'DAILY_ARENA'
                  AND t.status IN ('ROUND_1','ROUND_2','ROUND_3','ROUND_4','COMPLETED')
                  AND t.created_at >= :recent_cutoff
                  AND u.status = 'ACTIVE'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM telegram_delivery_attempts d
                    WHERE d.flow = 'daily_cup_round_messaging'
                      AND d.correlation_id = t.id::text
                      AND d.target_id LIKE (
                        p.user_id::text || ':phase:' ||
                        CASE
                          WHEN t.status = 'COMPLETED' THEN 'status:completed'
                          ELSE (
                            'round:' || GREATEST(1, t.current_round)::text ||
                            ':status:' || lower(t.status)
                          )
                        END || ':%'
                      )
                      AND d.status IN ('SENT','FAILED','SKIPPED')
                  )
            """,
            params={"recent_cutoff": recent_cutoff},
            description="Daily Cup participant is missing a terminal round delivery outcome.",
        ),
    ]
