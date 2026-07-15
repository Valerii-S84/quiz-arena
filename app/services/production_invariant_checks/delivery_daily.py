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
                WHERE t.type = 'DAILY_ARENA'
                  AND (
                    (
                      t.status IN ('ROUND_1','ROUND_2','ROUND_3','ROUND_4')
                      AND t.round_start_time >= GREATEST(:recent_cutoff, b.started_at)
                    )
                    OR (
                      t.status = 'COMPLETED'
                      AND EXISTS (
                        SELECT 1
                        FROM tournament_matches m
                        WHERE m.tournament_id = t.id
                          AND m.round_no = t.current_round
                          AND m.deadline >= GREATEST(:recent_cutoff, b.started_at)
                      )
                    )
                  )
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
                JOIN users u ON u.id = p.user_id
                CROSS JOIN reliability_baseline b
                WHERE t.type = 'DAILY_ARENA'
                  AND (
                    (
                      t.status IN ('ROUND_1','ROUND_2','ROUND_3','ROUND_4')
                      AND t.round_start_time >= GREATEST(:recent_cutoff, b.started_at)
                    )
                    OR (
                      t.status = 'COMPLETED'
                      AND EXISTS (
                        SELECT 1
                        FROM tournament_matches m
                        WHERE m.tournament_id = t.id
                          AND m.round_no = t.current_round
                          AND m.deadline >= GREATEST(:recent_cutoff, b.started_at)
                      )
                    )
                  )
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
            """

_CANCEL_MESSAGE_GAP_SQL = """
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
                JOIN users u ON u.id = p.user_id
                CROSS JOIN reliability_baseline b
                WHERE t.type = 'DAILY_ARENA'
                  AND t.status = 'CANCELED'
                  AND t.registration_deadline >= GREATEST(:recent_cutoff, b.started_at)
                  AND u.status = 'ACTIVE'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM telegram_delivery_attempts d
                    WHERE d.flow = 'daily_cup_cancel_message'
                      AND d.correlation_id = t.id::text
                      AND d.telegram_user_id = u.telegram_user_id
                      AND d.status IN ('SENT','FAILED','SKIPPED')
                  )
            """


def build_daily_cup_delivery_checks(recent_cutoff: datetime) -> list[InvariantCheck]:
    baseline_schedule_key = "__production_reliability_migration_baseline__"
    return [
        build_check(
            name="daily_cup_expected_delivery_zero_outcomes",
            severity=SEVERITY_P1,
            sql=_EXPECTED_DELIVERY_ZERO_OUTCOMES_SQL,
            params={
                "recent_cutoff": recent_cutoff,
                "baseline_schedule_key": baseline_schedule_key,
            },
            description="Recent Daily Cup expected messaging has zero durable outcomes.",
        ),
        build_check(
            name="daily_cup_round_delivery_gap",
            severity=SEVERITY_P1,
            sql=_ROUND_DELIVERY_GAP_SQL,
            params={
                "recent_cutoff": recent_cutoff,
                "baseline_schedule_key": baseline_schedule_key,
            },
            description="Daily Cup participant is missing a terminal round delivery outcome.",
        ),
        build_check(
            name="daily_cup_cancel_message_gap",
            severity=SEVERITY_P1,
            sql=_CANCEL_MESSAGE_GAP_SQL,
            params={
                "recent_cutoff": recent_cutoff,
                "baseline_schedule_key": baseline_schedule_key,
            },
            description="Canceled Daily Cup participant is missing a terminal cancel message.",
        ),
    ]
