from __future__ import annotations

from datetime import date

from app.game.questions.static_bank import (
    get_question_by_id,
    get_question_for_mode,
    select_question_for_mode,
)


def test_select_question_for_mode_uses_anti_repeat_candidates() -> None:
    selected = select_question_for_mode(
        "QUICK_MIX_A1A2",
        local_date_berlin=date(2026, 2, 18),
        recent_question_ids=["qm_a1a2_001", "qm_a1a2_002", "qm_a1a2_003"],
        selection_seed="seed-1",
    )
    assert selected.question_id == "qm_a1a2_004"


def test_select_question_for_mode_falls_back_to_full_pool_when_all_recent() -> None:
    selected = select_question_for_mode(
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 2, 18),
        recent_question_ids=[
            "artikel_001",
            "artikel_002",
            "artikel_003",
            "artikel_004",
        ],
        selection_seed="seed-2",
    )
    assert selected.question_id in {
        "artikel_001",
        "artikel_002",
        "artikel_003",
        "artikel_004",
    }


def test_select_question_for_mode_is_seed_deterministic() -> None:
    first = select_question_for_mode(
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 2, 18),
        recent_question_ids=[],
        selection_seed="same-seed",
    )
    second = select_question_for_mode(
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 2, 18),
        recent_question_ids=[],
        selection_seed="same-seed",
    )
    assert first.question_id == second.question_id


def test_get_question_by_id_returns_daily_question_for_matching_date() -> None:
    local_date = date(2026, 2, 18)
    question = get_question_for_mode("DAILY_CHALLENGE", local_date_berlin=local_date)
    resolved = get_question_by_id(
        "DAILY_CHALLENGE",
        question_id=question.question_id,
        local_date_berlin=local_date,
    )
    assert resolved is not None
    assert resolved.question_id == question.question_id


def test_get_question_by_id_returns_none_for_unknown_question() -> None:
    resolved = get_question_by_id(
        "QUICK_MIX_A1A2",
        question_id="unknown-question",
        local_date_berlin=date(2026, 2, 18),
    )
    assert resolved is None
