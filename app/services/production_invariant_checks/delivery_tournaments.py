from __future__ import annotations

from datetime import datetime

from app.services.production_invariant_checks.types import SEVERITY_P1, InvariantCheck, build_check


def build_tournament_delivery_checks(recent_cutoff: datetime) -> list[InvariantCheck]:
    return [
        build_check(
            name="tournament_round_expected_delivery_zero_outcomes",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM tournaments t
                WHERE t.type = 'PRIVATE'
                  AND (
                    t.status IN ('ROUND_1','ROUND_2','ROUND_3','ROUND_4','BRACKET_LIVE')
                    OR (
                      t.status = 'COMPLETED'
                      AND (
                        t.created_at >= :recent_cutoff
                        OR t.round_deadline >= :recent_cutoff
                        OR EXISTS (
                          SELECT 1
                          FROM tournament_matches m
                          WHERE m.tournament_id = t.id
                            AND m.deadline >= :recent_cutoff
                        )
                      )
                    )
                  )
                  AND EXISTS (
                    SELECT 1
                    FROM tournament_participants p
                    WHERE p.tournament_id = t.id
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM telegram_delivery_attempts d
                    WHERE d.flow = 'private_tournament_round_messaging'
                      AND d.correlation_id = t.id::text
                      AND d.status IN ('SENT','FAILED','SKIPPED')
                  )
            """,
            params={"recent_cutoff": recent_cutoff},
            description="Recent private tournament expected messaging has zero durable outcomes.",
        ),
        build_check(
            name="private_tournament_round_delivery_gap",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM tournament_participants p
                JOIN tournaments t ON t.id = p.tournament_id
                WHERE t.type = 'PRIVATE'
                  AND (
                    t.status IN ('ROUND_1','ROUND_2','ROUND_3','ROUND_4','BRACKET_LIVE')
                    OR (
                      t.status = 'COMPLETED'
                      AND (
                        t.created_at >= :recent_cutoff
                        OR t.round_deadline >= :recent_cutoff
                        OR EXISTS (
                          SELECT 1
                          FROM tournament_matches m
                          WHERE m.tournament_id = t.id
                            AND m.deadline >= :recent_cutoff
                        )
                      )
                    )
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM telegram_delivery_attempts d
                    WHERE d.flow = 'private_tournament_round_messaging'
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
            description="Private tournament participant is missing a terminal delivery outcome.",
        ),
    ]
