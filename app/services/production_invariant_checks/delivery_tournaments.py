from __future__ import annotations

from datetime import datetime

from app.services.production_invariant_checks.types import SEVERITY_P1, InvariantCheck, build_check

_EXPECTED_DELIVERY_ZERO_OUTCOMES_SQL = """
                WITH reliability_baseline AS (
                  SELECT COALESCE(
                    (
                      SELECT last_success_at
                      FROM worker_task_heartbeats
                      WHERE schedule_key = :baseline_schedule_key
                      LIMIT 1
                    ),
                    :recent_cutoff
                  ) AS started_at
                )
                SELECT count(*)
                FROM tournaments t
                CROSS JOIN reliability_baseline b
                WHERE t.type = 'PRIVATE'
                  AND (
                    (
                      t.status IN ('ROUND_1','ROUND_2','ROUND_3','ROUND_4','BRACKET_LIVE')
                      AND t.round_deadline >= :recent_cutoff
                      AND t.round_deadline >= b.started_at
                    )
                    OR (
                      t.status = 'COMPLETED'
                      AND EXISTS (
                        SELECT 1
                        FROM tournament_matches m
                        WHERE m.tournament_id = t.id
                          AND m.round_no = t.current_round
                          AND m.deadline >= :recent_cutoff
                          AND m.deadline >= b.started_at
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
            """

_ROUND_DELIVERY_GAP_SQL = """
                WITH reliability_baseline AS (
                  SELECT COALESCE(
                    (
                      SELECT last_success_at
                      FROM worker_task_heartbeats
                      WHERE schedule_key = :baseline_schedule_key
                      LIMIT 1
                    ),
                    :recent_cutoff
                  ) AS started_at
                )
                SELECT count(*)
                FROM tournament_participants p
                JOIN tournaments t ON t.id = p.tournament_id
                CROSS JOIN reliability_baseline b
                WHERE t.type = 'PRIVATE'
                  AND (
                    (
                      t.status IN ('ROUND_1','ROUND_2','ROUND_3','ROUND_4','BRACKET_LIVE')
                      AND t.round_deadline >= :recent_cutoff
                      AND t.round_deadline >= b.started_at
                    )
                    OR (
                      t.status = 'COMPLETED'
                      AND EXISTS (
                        SELECT 1
                        FROM tournament_matches m
                        WHERE m.tournament_id = t.id
                          AND m.round_no = t.current_round
                          AND m.deadline >= :recent_cutoff
                          AND m.deadline >= b.started_at
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
            """


def build_tournament_delivery_checks(recent_cutoff: datetime) -> list[InvariantCheck]:
    baseline_schedule_key = "__production_reliability_migration_baseline__"
    return [
        build_check(
            name="tournament_round_expected_delivery_zero_outcomes",
            severity=SEVERITY_P1,
            sql=_EXPECTED_DELIVERY_ZERO_OUTCOMES_SQL,
            params={
                "recent_cutoff": recent_cutoff,
                "baseline_schedule_key": baseline_schedule_key,
            },
            description="Recent private tournament expected messaging has zero durable outcomes.",
        ),
        build_check(
            name="private_tournament_round_delivery_gap",
            severity=SEVERITY_P1,
            sql=_ROUND_DELIVERY_GAP_SQL,
            params={
                "recent_cutoff": recent_cutoff,
                "baseline_schedule_key": baseline_schedule_key,
            },
            description="Private tournament participant is missing a terminal delivery outcome.",
        ),
    ]
