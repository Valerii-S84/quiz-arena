from __future__ import annotations

from dataclasses import dataclass, field

from app.services.messaging_repair_models import (
    ExistingDeliveryOutcome,
    MessagingRepairPlan,
    RepairTarget,
)
from app.services.messaging_repair_targets import phase_repair_match_id


@dataclass(slots=True)
class _RepairAttemptGroups:
    accounted_by_target: dict[tuple[str, str], ExistingDeliveryOutcome] = field(
        default_factory=dict
    )
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
    indeterminate_targets = [target for target in expected_targets if not target.is_matchable]
    missing_targets = [
        target
        for target in expected_targets
        if target.is_matchable
        and _repair_match_key(target_type=target.target_type, target_id=target.target_id)
        not in groups.accounted_by_target
    ]
    return MessagingRepairPlan(
        flow=flow,
        correlation_id=correlation_id,
        expected_targets=expected_targets,
        existing_attempts=existing_attempts,
        missing_targets=missing_targets,
        indeterminate_targets=indeterminate_targets,
        pending_targets=groups.pending_targets,
        stale_pending_targets=groups.stale_pending_targets,
        failed_targets=groups.failed_targets,
        skipped_targets=groups.skipped_targets,
        safe_replay_candidates=list(missing_targets),
    )


def _classify_existing_attempts(
    existing_attempts: list[ExistingDeliveryOutcome],
) -> _RepairAttemptGroups:
    groups = _RepairAttemptGroups()
    for attempt in existing_attempts:
        key = _repair_match_key(target_type=attempt.target_type, target_id=attempt.target_id)
        if attempt.status == "SENT":
            groups.accounted_by_target[key] = attempt
        elif attempt.status == "PENDING":
            groups.pending_targets.append(attempt)
            groups.accounted_by_target.setdefault(key, attempt)
            if attempt.is_stale_pending:
                groups.stale_pending_targets.append(attempt)
        elif attempt.status == "FAILED":
            groups.failed_targets.append(attempt)
            groups.accounted_by_target.setdefault(key, attempt)
        elif attempt.status == "SKIPPED":
            groups.skipped_targets.append(attempt)
            groups.accounted_by_target.setdefault(key, attempt)
    return groups


def _repair_match_key(*, target_type: str, target_id: str) -> tuple[str, str]:
    return (target_type, phase_repair_match_id(target_id))


__all__ = ["build_messaging_repair_plan"]
