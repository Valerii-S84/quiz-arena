from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.game.sessions.service.friend_challenges_question_plan import select_duel_question_ids
from tests.game.runtime_bank_fixtures import _fake_record
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_duel_question_plan_avoids_repeating_source_file_between_rounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = {
        "round_1_source_a": _fake_record("round_1_source_a", source_file="source_a.csv"),
        "round_2_same_source": _fake_record(
            "round_2_same_source",
            source_file="source_a.csv",
            category="Light",
        ),
        "round_2_new_source": _fake_record(
            "round_2_new_source",
            source_file="source_b.csv",
            category="General",
        ),
        "round_3_source_c": _fake_record("round_3_source_c", source_file="source_c.csv"),
        "round_4_source_d": _fake_record("round_4_source_d", source_file="source_d.csv"),
        "round_5_source_e": _fake_record("round_5_source_e", source_file="source_e.csv"),
    }

    async def fake_list_question_ids_all_active(  # noqa: ANN001
        session,
        *,
        exclude_question_ids=None,
        preferred_levels=None,
        require_quick_mix_eligible=False,
    ):
        selected = set(exclude_question_ids or ())
        if not selected:
            return ["round_1_source_a"]
        if selected == {"round_1_source_a"}:
            return ["round_2_same_source", "round_2_new_source"]
        return [
            question_id
            for question_id in ("round_3_source_c", "round_4_source_d", "round_5_source_e")
            if question_id not in selected
        ]

    async def fake_list_question_ids_for_mode(  # noqa: ANN001
        session,
        *,
        mode_code,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        return []

    async def fake_list_by_ids(session, *, question_ids):  # noqa: ANN001
        return [records[question_id] for question_id in question_ids if question_id in records]

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_all_active",
        fake_list_question_ids_all_active,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_for_mode",
        fake_list_question_ids_for_mode,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_by_ids",
        fake_list_by_ids,
    )

    selected = await select_duel_question_ids(
        _Session(),
        mode_code="QUICK_MIX_A1A2",
        total_rounds=5,
        now_utc=datetime(2026, 5, 7, 10, 0, tzinfo=UTC),
        challenge_seed="duel-source-diversity",
        preferred_levels_by_round=("A1", "A1", "A1", "A1", "A1"),
    )

    assert selected[0] == "round_1_source_a"
    assert selected[1] == "round_2_new_source"
    assert len(selected) == 5
