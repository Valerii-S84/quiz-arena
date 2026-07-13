from __future__ import annotations

from dataclasses import dataclass, field

from app.services.messaging_repair_models import (
    ExistingDeliveryOutcome,
    MessagingRepairPlan,
    RepairTarget,
)
from app.services.messaging_repair_targets import phase_repair_match_id
from app.services.telegram_delivery_types import MAX_DELIVERY_ATTEMPTS, RETRYABLE_FAILURE_CODES


@dataclass(slots=True)
class _RepairAttemptGroups:
    accounted_by_target: dict[tuple[str, str], ExistingDeliveryOutcome] = field(
        default_factory=dict
    )
    sent_target_keys: set[tuple[str, str]] = field(default_factory=set)
    pending_target_keys: set[tuple[str, str]] = field(default_factory=set)
    pending_targets: list[ExistingDeliveryOutcome] = field(default_factory=list)
    stale_pending_targets: list[ExistingDeliveryOutcome] = field(default_factory=list)
    failed_targets: list[ExistingDeliveryOutcome] = field(default_factory=list)
    skipped_targets: list[ExistingDeliveryOutcome] = field(default_factory=list)


def build_messaging_repair_plan(
    *,
    flow: str,
    correlation_id: str,
    expected_targets: list[RepairTarget],
    existing_attempts: list[ExistingDeliveryOutcome],
) -> MessagingRepairPlan:
    groups = _classify_existing_attempts(existing_attempts)
    missing_targets = [
        target
        for target in expected_targets
        if _repair_match_key(target_type=target.target_type, target_id=target.target_id)
        not in groups.accounted_by_target
    ]
    safe_replay_candidates = _build_safe_replay_candidates(
        flow=flow,
        expected_targets=expected_targets,
        missing_targets=missing_targets,
        groups=groups,
    )

    return MessagingRepairPlan(
        flow=flow,
        correlation_id=correlation_id,
        expected_targets=expected_targets,
        existing_attempts=existing_attempts,
        missing_targets=missing_targets,
        pending_targets=groups.pending_targets,
        stale_pending_targets=groups.stale_pending_targets,
        failed_targets=groups.failed_targets,
        skipped_targets=groups.skipped_targets,
        safe_replay_candidates=safe_replay_candidates,
    )


def _classify_existing_attempts(
    existing_attempts: list[ExistingDeliveryOutcome],
) -> _RepairAttemptGroups:
    groups = _RepairAttemptGroups()
    for attempt in existing_attempts:
        key = _repair_match_key(target_type=attempt.target_type, target_id=attempt.target_id)
        if attempt.status == "SENT":
            groups.accounted_by_target[key] = attempt
            groups.sent_target_keys.add(key)
            continue
        if attempt.status == "PENDING":
            groups.pending_targets.append(attempt)
            groups.pending_target_keys.add(key)
            groups.accounted_by_target.setdefault(key, attempt)
            if attempt.is_stale_pending:
                groups.stale_pending_targets.append(attempt)
            continue
        if attempt.status == "FAILED":
            groups.failed_targets.append(attempt)
            groups.accounted_by_target.setdefault(key, attempt)
            continue
        if attempt.status == "SKIPPED":
            groups.skipped_targets.append(attempt)
            groups.accounted_by_target.setdefault(key, attempt)
    return groups


def _build_safe_replay_candidates(
    *,
    flow: str,
    expected_targets: list[RepairTarget],
    missing_targets: list[RepairTarget],
    groups: _RepairAttemptGroups,
) -> list[RepairTarget]:
    safe_replay_candidates = list(missing_targets)
    expected_target_keys = {
        _repair_match_key(target_type=target.target_type, target_id=target.target_id)
        for target in expected_targets
    }
    for attempt in groups.failed_targets:
        key = _repair_match_key(target_type=attempt.target_type, target_id=attempt.target_id)
        if (
            flow
            in {
                "daily_cup_round_messaging",
                "private_tournament_round_messaging",
            }
            and key not in expected_target_keys
        ):
            continue
        if key in groups.sent_target_keys or key in groups.pending_target_keys:
            continue
        if not _failed_attempt_is_replay_safe(attempt):
            continue
        if any(
            _repair_match_key(target_type=candidate.target_type, target_id=candidate.target_id)
            == key
            for candidate in safe_replay_candidates
        ):
            continue
        replay_target = RepairTarget(target_type=attempt.target_type, target_id=attempt.target_id)
        safe_replay_candidates.append(replay_target)
    return safe_replay_candidates


def _repair_match_key(*, target_type: str, target_id: str) -> tuple[str, str]:
    return (target_type, phase_repair_match_id(target_id))


def _failed_attempt_is_replay_safe(attempt: ExistingDeliveryOutcome) -> bool:
    return (
        attempt.pending_replay_safe
        and attempt.failure_code in RETRYABLE_FAILURE_CODES
        and attempt.attempt_count < MAX_DELIVERY_ATTEMPTS
    )


__all__ = ["build_messaging_repair_plan"]
