from __future__ import annotations

from app.services.messaging_repair_planner import (
    ExistingDeliveryOutcome,
    RepairTarget,
    build_messaging_repair_plan,
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
                failure_code="TELEGRAM_FORBIDDEN",
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


def test_repair_plan_matches_operation_shaped_delivery_target_ids_by_user() -> None:
    plan = build_messaging_repair_plan(
        flow="daily_cup_round_messaging",
        correlation_id="cup-1",
        expected_targets=[
            RepairTarget(target_type="user", target_id="1"),
            RepairTarget(target_type="user", target_id="2"),
            RepairTarget(target_type="user", target_id="3"),
        ],
        existing_attempts=[
            ExistingDeliveryOutcome(target_type="user", target_id="1:send", status="FAILED"),
            ExistingDeliveryOutcome(target_type="user", target_id="1:edit:101", status="SENT"),
            ExistingDeliveryOutcome(target_type="user", target_id="2:send", status="FAILED"),
        ],
    )

    assert [target.target_id for target in plan.missing_targets] == ["3"]
    assert [target.target_id for target in plan.safe_replay_candidates] == ["3", "2"]


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
