from __future__ import annotations

from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.messaging_repair_planner import (
    ExistingDeliveryOutcome,
    RepairTarget,
    build_messaging_repair_plan,
    plan_tournament_messaging_repair,
)
from app.services.telegram_delivery_types import (
    FAILURE_CODE_FORBIDDEN,
    FAILURE_CODE_RETRY_AFTER,
    MAX_DELIVERY_ATTEMPTS,
)


def test_repair_plan_finds_missing_daily_cup_targets() -> None:
    plan = build_messaging_repair_plan(
        flow="daily_cup_round_messaging",
        correlation_id="cup-1",
        expected_targets=[
            RepairTarget(target_type="user", target_id="1"),
            RepairTarget(target_type="user", target_id="2"),
        ],
        existing_attempts=[
            ExistingDeliveryOutcome(target_type="user", target_id="1", status="SENT"),
        ],
    )

    assert plan.dry_run is True
    assert plan.missing_targets == [RepairTarget(target_type="user", target_id="2")]
    assert plan.safe_replay_candidates == [RepairTarget(target_type="user", target_id="2")]


def test_repair_plan_finds_failed_tournament_targets_without_sent_duplicates() -> None:
    plan = build_messaging_repair_plan(
        flow="private_tournament_round_messaging",
        correlation_id="tournament-1",
        expected_targets=[
            RepairTarget(target_type="user", target_id="1"),
            RepairTarget(target_type="user", target_id="2"),
        ],
        existing_attempts=[
            ExistingDeliveryOutcome(target_type="user", target_id="1", status="SENT"),
            ExistingDeliveryOutcome(
                target_type="user",
                target_id="2",
                status="FAILED",
                failure_code=FAILURE_CODE_RETRY_AFTER,
            ),
        ],
    )

    assert plan.missing_targets == []
    assert [target.target_id for target in plan.safe_replay_candidates] == ["2"]
    assert [target.target_id for target in plan.failed_targets] == ["2"]


def test_repair_plan_never_replays_target_with_sent_outcome() -> None:
    plan = build_messaging_repair_plan(
        flow="private_tournament_round_messaging",
        correlation_id="tournament-1",
        expected_targets=[RepairTarget(target_type="user", target_id="1")],
        existing_attempts=[
            ExistingDeliveryOutcome(target_type="user", target_id="1", status="FAILED"),
            ExistingDeliveryOutcome(target_type="user", target_id="1", status="SENT"),
        ],
    )

    assert plan.failed_targets[0].target_id == "1"
    assert plan.safe_replay_candidates == []


def test_repair_plan_keeps_phase_specific_delivery_target_ids() -> None:
    plan = build_messaging_repair_plan(
        flow="daily_cup_round_messaging",
        correlation_id="cup-1",
        expected_targets=[
            RepairTarget(target_type="user", target_id="1:phase:round:2:status:round_2:edit:101"),
            RepairTarget(target_type="user", target_id="2:phase:round:2:status:round_2:edit:202"),
        ],
        existing_attempts=[
            ExistingDeliveryOutcome(
                target_type="user",
                target_id="1:phase:round:1:status:round_1:edit:101",
                status="SENT",
            ),
            ExistingDeliveryOutcome(
                target_type="user",
                target_id="2:phase:round:2:status:round_2:edit:202",
                status="SENT",
            ),
        ],
    )

    assert [target.target_id for target in plan.missing_targets] == [
        "1:phase:round:2:status:round_2:edit:101"
    ]
    assert [target.target_id for target in plan.safe_replay_candidates] == [
        "1:phase:round:2:status:round_2:edit:101"
    ]


def test_repair_plan_excludes_permanent_failures_from_safe_replay() -> None:
    target_id = "1:phase:status:completed:send"
    plan = build_messaging_repair_plan(
        flow="private_tournament_round_messaging",
        correlation_id="tournament-1",
        expected_targets=[RepairTarget(target_type="user", target_id=target_id)],
        existing_attempts=[
            ExistingDeliveryOutcome(
                target_type="user",
                target_id=target_id,
                status="FAILED",
                failure_code=FAILURE_CODE_FORBIDDEN,
            ),
        ],
    )

    assert plan.failed_targets[0].failure_code == FAILURE_CODE_FORBIDDEN
    assert plan.safe_replay_candidates == []


def test_repair_plan_excludes_retryable_failures_after_max_attempts() -> None:
    target_id = "1:phase:round:2:status:round_2:send"
    plan = build_messaging_repair_plan(
        flow="private_tournament_round_messaging",
        correlation_id="tournament-1",
        expected_targets=[RepairTarget(target_type="user", target_id=target_id)],
        existing_attempts=[
            ExistingDeliveryOutcome(
                target_type="user",
                target_id=target_id,
                status="FAILED",
                attempt_count=MAX_DELIVERY_ATTEMPTS,
                failure_code=FAILURE_CODE_RETRY_AFTER,
            ),
        ],
    )

    assert plan.safe_replay_candidates == []


def test_repair_plan_keeps_final_and_cancel_targets_distinct() -> None:
    plan = build_messaging_repair_plan(
        flow="daily_cup_round_messaging",
        correlation_id="cup-1",
        expected_targets=[
            RepairTarget(target_type="user", target_id="1:phase:status:completed:send"),
            RepairTarget(target_type="chat_hash", target_id="abc:status:canceled"),
        ],
        existing_attempts=[
            ExistingDeliveryOutcome(
                target_type="user",
                target_id="1:phase:status:completed:send",
                status="SENT",
            ),
        ],
    )

    assert plan.missing_targets == [
        RepairTarget(target_type="chat_hash", target_id="abc:status:canceled")
    ]
    assert plan.safe_replay_candidates == [
        RepairTarget(target_type="chat_hash", target_id="abc:status:canceled")
    ]


async def test_repair_plan_loader_builds_current_phase_targets() -> None:
    session = _RepairPlanSession(
        expected_rows=[
            (1, 101, "ROUND_2", 2),
            (2, None, "ROUND_2", 2),
        ],
        existing_rows=[
            (
                "user",
                "1:phase:round:1:status:round_1:edit:101",
                "SENT",
                1,
                None,
            )
        ],
    )

    plan = await plan_tournament_messaging_repair(
        cast(AsyncSession, session),
        flow="daily_cup_round_messaging",
        tournament_id="cup-1",
    )

    assert [target.target_id for target in plan.missing_targets] == [
        "1:phase:round:2:status:round_2:edit:101",
        "2:phase:round:2:status:round_2:send",
    ]


def test_repair_plan_keeps_skipped_out_of_replay_candidates() -> None:
    plan = build_messaging_repair_plan(
        flow="private_tournament_round_messaging",
        correlation_id="tournament-2",
        expected_targets=[
            RepairTarget(target_type="user", target_id="1"),
            RepairTarget(target_type="user", target_id="2"),
        ],
        existing_attempts=[
            ExistingDeliveryOutcome(target_type="user", target_id="1", status="SKIPPED"),
            ExistingDeliveryOutcome(target_type="user", target_id="2", status="SENT"),
        ],
    )

    assert [target.target_id for target in plan.skipped_targets] == ["1"]
    assert plan.safe_replay_candidates == []


class _RowsResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


class _RepairPlanSession:
    def __init__(
        self,
        *,
        expected_rows: list[tuple[object, ...]],
        existing_rows: list[tuple[object, ...]],
    ) -> None:
        self._results = [_RowsResult(expected_rows), _RowsResult(existing_rows)]

    async def execute(self, *_args, **_kwargs) -> _RowsResult:
        return self._results.pop(0)
