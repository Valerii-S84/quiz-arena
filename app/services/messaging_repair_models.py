from __future__ import annotations

from dataclasses import dataclass


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
    is_stale_pending: bool = False
    pending_replay_safe: bool = False


@dataclass(frozen=True, slots=True)
class MessagingRepairPlan:
    flow: str
    correlation_id: str
    expected_targets: list[RepairTarget]
    existing_attempts: list[ExistingDeliveryOutcome]
    missing_targets: list[RepairTarget]
    pending_targets: list[ExistingDeliveryOutcome]
    stale_pending_targets: list[ExistingDeliveryOutcome]
    failed_targets: list[ExistingDeliveryOutcome]
    skipped_targets: list[ExistingDeliveryOutcome]
    safe_replay_candidates: list[RepairTarget]
    dry_run: bool = True


__all__ = "ExistingDeliveryOutcome MessagingRepairPlan RepairTarget".split()
