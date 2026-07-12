from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.messaging_repair_targets import phase_repair_target_id
from app.services.telegram_delivery_types import MAX_DELIVERY_ATTEMPTS, RETRYABLE_FAILURE_CODES


@dataclass(frozen=True, slots=True)
class RepairTarget:
    target_type: str
    target_id: str


@dataclass(frozen=True, slots=True)
class ExistingDeliveryOutcome:
    target_type: str
    target_id: str
    status: str
    attempt_count: int = 0
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class MessagingRepairPlan:
    flow: str
    correlation_id: str
    expected_targets: list[RepairTarget]
    existing_attempts: list[ExistingDeliveryOutcome]
    missing_targets: list[RepairTarget]
    failed_targets: list[ExistingDeliveryOutcome]
    skipped_targets: list[ExistingDeliveryOutcome]
    safe_replay_candidates: list[RepairTarget]
    dry_run: bool = True


def build_messaging_repair_plan(
    *,
    flow: str,
    correlation_id: str,
    expected_targets: list[RepairTarget],
    existing_attempts: list[ExistingDeliveryOutcome],
) -> MessagingRepairPlan:
    terminal_by_target: dict[tuple[str, str], ExistingDeliveryOutcome] = {}
    sent_target_keys: set[tuple[str, str]] = set()
    failed_targets: list[ExistingDeliveryOutcome] = []
    skipped_targets: list[ExistingDeliveryOutcome] = []
    for attempt in existing_attempts:
        key = _repair_match_key(target_type=attempt.target_type, target_id=attempt.target_id)
        if attempt.status == "SENT":
            terminal_by_target[key] = attempt
            sent_target_keys.add(key)
        elif attempt.status == "FAILED":
            failed_targets.append(attempt)
            terminal_by_target.setdefault(key, attempt)
        elif attempt.status == "SKIPPED":
            skipped_targets.append(attempt)
            terminal_by_target.setdefault(key, attempt)

    missing_targets = [
        target
        for target in expected_targets
        if _repair_match_key(target_type=target.target_type, target_id=target.target_id)
        not in terminal_by_target
    ]
    safe_replay_candidates = list(missing_targets)
    for attempt in failed_targets:
        key = _repair_match_key(target_type=attempt.target_type, target_id=attempt.target_id)
        if key in sent_target_keys:
            continue
        if not _failed_attempt_is_replay_safe(attempt):
            continue
        if any(
            _repair_match_key(target_type=candidate.target_type, target_id=candidate.target_id)
            == key
            for candidate in safe_replay_candidates
        ):
            continue
        safe_replay_candidates.append(RepairTarget(target_type=key[0], target_id=key[1]))

    return MessagingRepairPlan(
        flow=flow,
        correlation_id=correlation_id,
        expected_targets=expected_targets,
        existing_attempts=existing_attempts,
        missing_targets=missing_targets,
        failed_targets=failed_targets,
        skipped_targets=skipped_targets,
        safe_replay_candidates=safe_replay_candidates,
    )


def _repair_match_key(*, target_type: str, target_id: str) -> tuple[str, str]:
    return (target_type, target_id)


def _failed_attempt_is_replay_safe(attempt: ExistingDeliveryOutcome) -> bool:
    return (
        attempt.failure_code in RETRYABLE_FAILURE_CODES
        and attempt.attempt_count < MAX_DELIVERY_ATTEMPTS
    )


async def plan_tournament_messaging_repair(
    session: AsyncSession,
    *,
    flow: str,
    tournament_id: str,
) -> MessagingRepairPlan:
    if flow not in {"daily_cup_round_messaging", "private_tournament_round_messaging"}:
        raise ValueError("unsupported repair flow")
    expected_targets = await _load_tournament_expected_targets(
        session,
        flow=flow,
        tournament_id=tournament_id,
    )
    existing_attempts = await _load_delivery_attempts(
        session,
        flow=flow,
        correlation_id=tournament_id,
    )
    return build_messaging_repair_plan(
        flow=flow,
        correlation_id=tournament_id,
        expected_targets=expected_targets,
        existing_attempts=existing_attempts,
    )


async def _load_tournament_expected_targets(
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
        {"tournament_id": tournament_id},
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


async def _load_delivery_attempts(
    session: AsyncSession,
    *,
    flow: str,
    correlation_id: str,
) -> list[ExistingDeliveryOutcome]:
    result = await session.execute(
        text(
            """
            SELECT target_type, target_id, status, attempt_count, failure_code
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
        )
        for row in result.all()
    ]


__all__ = [
    "ExistingDeliveryOutcome",
    "MessagingRepairPlan",
    "RepairTarget",
    "build_messaging_repair_plan",
    "plan_tournament_messaging_repair",
]
