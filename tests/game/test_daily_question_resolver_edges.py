from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.game.sessions.errors import DailyChallengeAlreadyPlayedError
from app.game.sessions.service import daily_question_resolver
from tests.type_helpers import AsyncSessionStub


class _Session(AsyncSessionStub):
    pass


def _question(*, question_id: str, level: str) -> SimpleNamespace:
    return SimpleNamespace(
        question_id=question_id,
        text=f"Question {question_id}",
        options=("a", "b", "c", "d"),
        level=level,
        category="Daily",
    )


@pytest.mark.asyncio
async def test_resolver_raises_when_daily_set_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        daily_question_resolver,
        "ensure_daily_question_set",
        _async_return(()),
    )

    with pytest.raises(DailyChallengeAlreadyPlayedError):
        await daily_question_resolver.resolve_daily_question_for_position(
            _Session(),
            berlin_date=date(2026, 3, 4),
            position=1,
        )


@pytest.mark.asyncio
async def test_resolver_clamps_position_and_falls_back_when_seed_question_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_question_ids: list[str] = []
    fallback_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        daily_question_resolver,
        "ensure_daily_question_set",
        _async_return(("q-1", "q-2")),
    )

    async def _fake_get_question_by_id(_session, _mode_code, *, question_id, local_date_berlin):
        loaded_question_ids.append(question_id)
        assert local_date_berlin == date(2026, 3, 4)
        return None

    async def _fake_select_question_for_mode(_session, _mode_code, **kwargs):
        fallback_calls.append(kwargs)
        return _question(question_id="fallback-q", level="B1")

    monkeypatch.setattr("app.game.sessions.service.get_question_by_id", _fake_get_question_by_id)
    monkeypatch.setattr(
        "app.game.sessions.service.select_question_for_mode",
        _fake_select_question_for_mode,
    )

    question_id, question = await daily_question_resolver.resolve_daily_question_for_position(
        _Session(),
        berlin_date=date(2026, 3, 4),
        position=99,
    )

    assert loaded_question_ids == ["q-2"]
    assert question_id == "fallback-q"
    assert question.question_id == "fallback-q"
    assert fallback_calls[0]["selection_seed"] == "daily:resolver:fallback:2026-03-04:99"
    assert fallback_calls[0]["preferred_level"] == "B1"
    assert fallback_calls[0]["allowed_levels"] == ("A1", "A2", "B1")


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
