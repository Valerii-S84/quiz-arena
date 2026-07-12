from __future__ import annotations

from app.services.messaging_repair_models import (
    ExistingDeliveryOutcome,
    MessagingRepairPlan,
    RepairTarget,
)
from app.services.messaging_repair_targets import phase_repair_match_id
from app.services.telegram_delivery_types import MAX_DELIVERY_ATTEMPTS, RETRYABLE_FAILURE_CODES


def build_messaging_repair_plan(
    *,
    flow: str,
    correlation_id: str,
    expected_targets: list[RepairTarget],
    existing_attempts: list[ExistingDeliveryOutcome],
) -> MessagingRepairPlan:
    accounted_by_target: dict[tuple[str, str], ExistingDeliveryOutcome] = {}
    sent_target_keys: set[tuple[str, str]] = set()
    pending_target_keys: set[tuple[str, str]] = set()
    pending_targets: list[ExistingDeliveryOutcome] = []
    stale_pending_targets: list[ExistingDeliveryOutcome] = []
    failed_targets: list[ExistingDeliveryOutcome] = []
    skipped_targets: list[ExistingDeliveryOutcome] = []
    for attempt in existing_attempts:
        key = _repair_match_key(target_type=attempt.target_type, target_id=attempt.target_id)
        if attempt.status == "SENT":
            accounted_by_target[key] = attempt
            sent_target_keys.add(key)
        elif attempt.status == "PENDING":
            pending_targets.append(attempt)
            pending_target_keys.add(key)
            accounted_by_target.setdefault(key, attempt)
            if attempt.is_stale_pending:
                stale_pending_targets.append(attempt)
        elif attempt.status == "FAILED":
            failed_targets.append(attempt)
            accounted_by_target.setdefault(key, attempt)
        elif attempt.status == "SKIPPED":
            skipped_targets.append(attempt)
            accounted_by_target.setdefault(key, attempt)

    missing_targets = [
        target
        for target in expected_targets
        if _repair_match_key(target_type=target.target_type, target_id=target.target_id)
        not in accounted_by_target
    ]
    safe_replay_candidates = list(missing_targets)
    for attempt in failed_targets:
        key = _repair_match_key(target_type=attempt.target_type, target_id=attempt.target_id)
        if key in sent_target_keys or key in pending_target_keys:
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

    return MessagingRepairPlan(
        flow=flow,
        correlation_id=correlation_id,
        expected_targets=expected_targets,
        existing_attempts=existing_attempts,
        missing_targets=missing_targets,
        pending_targets=pending_targets,
        stale_pending_targets=stale_pending_targets,
        failed_targets=failed_targets,
        skipped_targets=skipped_targets,
        safe_replay_candidates=safe_replay_candidates,
    )


def _repair_match_key(*, target_type: str, target_id: str) -> tuple[str, str]:
    return (target_type, phase_repair_match_id(target_id))


def _failed_attempt_is_replay_safe(attempt: ExistingDeliveryOutcome) -> bool:
    return (
        attempt.failure_code in RETRYABLE_FAILURE_CODES
        and attempt.attempt_count < MAX_DELIVERY_ATTEMPTS
    )


__all__ = ["build_messaging_repair_plan"]
