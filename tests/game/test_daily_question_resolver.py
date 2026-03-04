from __future__ import annotations

from datetime import date

import pytest

from app.game.questions.types import QuizQuestion
from app.game.sessions.service import daily_question_resolver


def _question(*, question_id: str, level: str) -> QuizQuestion:
    return QuizQuestion(
        question_id=question_id,
        text=f"Question {question_id}",
        options=("a", "b", "c", "d"),
        correct_option=0,
        level=level,
        category="DailyTest",
    )


@pytest.mark.asyncio
async def test_resolver_uses_daily_set_question_when_level_is_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure_daily_question_set(session, *, berlin_date):  # noqa: ANN001
        del session, berlin_date
        return ("q_a1_seed",)

    async def fake_get_question_by_id(  # noqa: ANN001
        session,
        mode_code,
        *,
        question_id,
        local_date_berlin,
    ):
        del session, mode_code, local_date_berlin
        return _question(question_id=question_id, level="A1")

    async def fail_select_question_for_mode(*args, **kwargs):  # noqa: ANN002, ANN003, ANN001
        del args, kwargs
        raise AssertionError("fallback selector must not be called for a valid daily level")

    monkeypatch.setattr(
        daily_question_resolver,
        "ensure_daily_question_set",
        fake_ensure_daily_question_set,
    )
    monkeypatch.setattr(
        "app.game.sessions.service.get_question_by_id",
        fake_get_question_by_id,
    )
    monkeypatch.setattr(
        "app.game.sessions.service.select_question_for_mode",
        fail_select_question_for_mode,
    )

    question_id, question = await daily_question_resolver.resolve_daily_question_for_position(
        object(),
        berlin_date=date(2026, 3, 4),
        position=1,
    )

    assert question_id == "q_a1_seed"
    assert question.question_id == "q_a1_seed"
    assert question.level == "A1"


@pytest.mark.asyncio
async def test_resolver_reselects_when_daily_set_question_level_is_out_of_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure_daily_question_set(session, *, berlin_date):  # noqa: ANN001
        del session, berlin_date
        return ("q_b2_seed",)

    async def fake_get_question_by_id(  # noqa: ANN001
        session,
        mode_code,
        *,
        question_id,
        local_date_berlin,
    ):
        del session, mode_code, question_id, local_date_berlin
        return _question(question_id="q_b2_seed", level="B2")

    captured: dict[str, object] = {}

    async def fake_select_question_for_mode(  # noqa: ANN001
        session,
        mode_code,
        *,
        local_date_berlin,
        recent_question_ids,
        selection_seed,
        preferred_level=None,
        allowed_levels=None,
    ):
        del session, mode_code, local_date_berlin, recent_question_ids, selection_seed
        captured["preferred_level"] = preferred_level
        captured["allowed_levels"] = tuple(allowed_levels or ())
        return _question(question_id="q_a1_replacement", level="A1")

    monkeypatch.setattr(
        daily_question_resolver,
        "ensure_daily_question_set",
        fake_ensure_daily_question_set,
    )
    monkeypatch.setattr(
        "app.game.sessions.service.get_question_by_id",
        fake_get_question_by_id,
    )
    monkeypatch.setattr(
        "app.game.sessions.service.select_question_for_mode",
        fake_select_question_for_mode,
    )

    question_id, question = await daily_question_resolver.resolve_daily_question_for_position(
        object(),
        berlin_date=date(2026, 3, 4),
        position=1,
    )

    assert question_id == "q_a1_replacement"
    assert question.question_id == "q_a1_replacement"
    assert question.level == "A1"
    assert captured["preferred_level"] == "A1"
    assert captured["allowed_levels"] == ("A1",)
