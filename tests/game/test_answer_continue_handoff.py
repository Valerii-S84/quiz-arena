from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.game.questions.types import QuizQuestion
from app.game.sessions.service import sessions_start_runtime
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_next_question_reuses_answer_handoff_and_excludes_answered_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _unexpected_progression_lookup(*_args, **_kwargs):
        pytest.fail("handoff data should avoid another mode progress lookup")

    async def _unexpected_recent_lookup(*_args, **_kwargs):
        pytest.fail("recent override should avoid another recent-attempt query")

    async def _select_question(_session, mode_code, **kwargs):
        captured.update({"mode_code": mode_code, **kwargs})
        return _question("next-q")

    monkeypatch.setattr(
        sessions_start_runtime.QuizAttemptsRepo,
        "get_recent_question_ids_for_mode",
        _unexpected_recent_lookup,
    )
    monkeypatch.setattr(
        "app.game.sessions.service.select_question_for_mode",
        _select_question,
    )

    selected = await sessions_start_runtime._resolve_start_question(
        AsyncSessionStub(),
        user_id=11,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        local_date=date(2026, 6, 18),
        selection_seed_override=None,
        idempotency_key="start:auto",
        now_utc=NOW_UTC,
        forced_question_id=None,
        preferred_question_level="A2",
        preferred_question_mix_step=1,
        recent_question_ids_override=("answered-q",),
        resolve_start_progression_state=_unexpected_progression_lookup,
        select_level_weighted=lambda *_args, **_kwargs: "B1",
        is_persistent_adaptive_mode=lambda *, mode_code: True,
    )

    assert selected.question_id == "next-q"
    assert captured["recent_question_ids"] == ["answered-q"]
    assert captured["preferred_level"] == "B1"
    assert captured["allowed_levels"] == ("A2", "B1")


@pytest.mark.asyncio
async def test_next_question_falls_back_to_progress_lookup_when_handoff_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _resolve_progression(*_args, **kwargs):
        captured["progression"] = kwargs
        return "A2", 0, ("A2",)

    async def _recent_questions(*_args, **kwargs):
        captured["recent_lookup"] = kwargs
        return ["older-q"]

    async def _select_question(_session, mode_code, **kwargs):
        captured.update({"mode_code": mode_code, **kwargs})
        return _question("fallback-q")

    monkeypatch.setattr(
        sessions_start_runtime.QuizAttemptsRepo,
        "get_recent_question_ids_for_mode",
        _recent_questions,
    )
    monkeypatch.setattr(
        "app.game.sessions.service.select_question_for_mode",
        _select_question,
    )

    selected = await sessions_start_runtime._resolve_start_question(
        AsyncSessionStub(),
        user_id=11,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        local_date=date(2026, 6, 18),
        selection_seed_override="seed",
        idempotency_key="start:fallback",
        now_utc=NOW_UTC,
        forced_question_id=None,
        preferred_question_level=None,
        preferred_question_mix_step=None,
        recent_question_ids_override=None,
        resolve_start_progression_state=_resolve_progression,
        select_level_weighted=lambda level, *_args, **_kwargs: level,
        is_persistent_adaptive_mode=lambda *, mode_code: True,
    )

    assert selected.question_id == "fallback-q"
    assert captured["progression"]["user_id"] == 11
    assert captured["recent_lookup"]["limit"] == 20
    assert captured["recent_question_ids"] == ["older-q"]
    assert captured["preferred_level"] == "A2"
    assert captured["allowed_levels"] == ("A2",)


def _question(question_id: str) -> QuizQuestion:
    return QuizQuestion(
        question_id=question_id,
        text="Frage?",
        options=("A", "B", "C", "D"),
        correct_option=1,
        level="A2",
        category="Grammatik",
    )
