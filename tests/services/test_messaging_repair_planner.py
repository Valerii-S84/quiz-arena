from __future__ import annotations

from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.messaging_repair_planner import (
    ExistingDeliveryOutcome,
    RepairTarget,
    build_messaging_repair_plan,
    plan_tournament_messaging_repair,
)
from app.services.messaging_repair_targets import phase_repair_match_id


def test_repair_plan_reports_missing_targets_as_dry_run_candidates() -> None:
    plan = build_messaging_repair_plan(
        flow="private_tournament_round_messaging",
        correlation_id="tournament-1",
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


def test_repair_plan_never_blindly_replays_pending_or_failed_attempts() -> None:
    plan = build_messaging_repair_plan(
        flow="private_tournament_round_messaging",
        correlation_id="tournament-1",
        expected_targets=[
            RepairTarget(target_type="user", target_id="1"),
            RepairTarget(target_type="user", target_id="2"),
        ],
        existing_attempts=[
            ExistingDeliveryOutcome(
                target_type="user",
                target_id="1",
                status="PENDING",
                failure_code="TELEGRAM_RETRY_NEEDED",
                is_stale_pending=True,
                pending_replay_safe=True,
            ),
            ExistingDeliveryOutcome(
                target_type="user",
                target_id="2",
                status="FAILED",
                failure_code="TELEGRAM_TRANSIENT_SEND_ERROR",
                pending_replay_safe=True,
            ),
        ],
    )

    assert [target.target_id for target in plan.pending_targets] == ["1"]
    assert [target.target_id for target in plan.stale_pending_targets] == ["1"]
    assert [target.target_id for target in plan.failed_targets] == ["2"]
    assert plan.safe_replay_candidates == []


def test_repair_target_matching_preserves_content_digest() -> None:
    previous_edit = "1:phase:round:2:status:round_2:c:abc123:edit:101"
    current_edit = "1:phase:round:2:status:round_2:c:def456:edit:101"
    fallback = "1:phase:round:2:status:round_2:fallback_send_after_edit:101"

    assert phase_repair_match_id(previous_edit).endswith(":c:abc123")
    assert phase_repair_match_id(previous_edit) != phase_repair_match_id(current_edit)
    assert phase_repair_match_id(previous_edit) != phase_repair_match_id(fallback)


def test_repair_plan_marks_edit_without_current_digest_indeterminate() -> None:
    expected_target = RepairTarget(
        target_type="user",
        target_id="1:phase:round:2:status:round_2:edit:902",
        is_matchable=False,
    )
    plan = build_messaging_repair_plan(
        flow="private_tournament_round_messaging",
        correlation_id="tournament-1",
        expected_targets=[expected_target],
        existing_attempts=[
            ExistingDeliveryOutcome(
                target_type="user",
                target_id="1:phase:round:2:status:round_2:c:abc123:edit:101",
                status="SENT",
            )
        ],
    )

    assert plan.indeterminate_targets == [expected_target]
    assert plan.missing_targets == []
    assert plan.safe_replay_candidates == []


def test_repair_plan_keeps_previous_phase_distinct() -> None:
    expected_target = RepairTarget(
        target_type="user",
        target_id="1:phase:round:2:status:round_2:edit:902",
    )
    plan = build_messaging_repair_plan(
        flow="private_tournament_round_messaging",
        correlation_id="tournament-1",
        expected_targets=[expected_target],
        existing_attempts=[
            ExistingDeliveryOutcome(
                target_type="user",
                target_id="1:phase:round:1:status:round_1:fallback_send_after_edit:101",
                status="SENT",
            )
        ],
    )

    assert plan.missing_targets == [expected_target]
    assert plan.safe_replay_candidates == [expected_target]


def test_repair_plan_keeps_skipped_targets_out_of_candidates() -> None:
    target = RepairTarget(target_type="user", target_id="1")
    plan = build_messaging_repair_plan(
        flow="private_tournament_round_messaging",
        correlation_id="tournament-1",
        expected_targets=[target],
        existing_attempts=[
            ExistingDeliveryOutcome(target_type="user", target_id="1", status="SKIPPED"),
        ],
    )

    assert plan.skipped_targets[0].target_id == "1"
    assert plan.safe_replay_candidates == []


async def test_loader_builds_current_phase_targets_and_uses_current_pending_ttl() -> None:
    tournament_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
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
                False,
                False,
            )
        ],
    )

    plan = await plan_tournament_messaging_repair(
        cast(AsyncSession, session),
        flow="private_tournament_round_messaging",
        tournament_id=tournament_id,
    )

    assert plan.indeterminate_targets == [
        RepairTarget(
            target_type="user",
            target_id="1:phase:round:2:status:round_2:edit:101",
            is_matchable=False,
        )
    ]
    assert [target.target_id for target in plan.missing_targets] == [
        "2:phase:round:2:status:round_2:send"
    ]
    assert "t.type = 'PRIVATE'" in session.statements[0]
    assert "t.status NOT IN ('REGISTRATION', 'CANCELED')" in session.statements[0]
    assert "interval '5 minutes'" in session.statements[1]
    assert session.params == [
        {"tournament_id": UUID(tournament_id)},
        {"flow": "private_tournament_round_messaging", "correlation_id": tournament_id},
    ]


async def test_planner_rejects_unsupported_daily_cup_flow() -> None:
    session = _RepairPlanSession(expected_rows=[], existing_rows=[])

    with pytest.raises(ValueError, match="unsupported repair flow"):
        await plan_tournament_messaging_repair(
            cast(AsyncSession, session),
            flow="daily_cup_round_messaging",
            tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        )

    assert session.statements == []


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
        self.statements: list[str] = []
        self.params: list[dict[str, object]] = []

    async def execute(self, statement, params, *_args, **_kwargs) -> _RowsResult:
        self.statements.append(str(statement))
        self.params.append(params)
        return self._results.pop(0)
