from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.game.sessions.service import friend_challenges_rounds, friend_challenges_rounds_start
from tests.game.friend_challenges_unit_support import (
    NOW_UTC,
    Session,
    async_return,
    challenge,
    start_result,
)


@pytest.mark.asyncio
async def test_round_start_selects_question_when_plan_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(question_ids=[])
    selection_calls: list[dict[str, object]] = []
    start_calls: list[dict[str, object]] = []

    await _start_with_selected_question(monkeypatch, row, selection_calls, start_calls)

    assert selection_calls[0]["previous_round_question_ids"] == ["old-q"]
    assert selection_calls[0]["preferred_level"] == "A1"
    assert start_calls[0]["forced_question_id"] == "selected-q"
    assert start_calls[0]["friend_challenge_round"] == 1


@pytest.mark.asyncio
async def test_round_start_falls_back_when_plan_has_no_next_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(creator_answered_round=4, question_ids=["q-1"], total_rounds=7)
    selection_calls: list[dict[str, object]] = []
    start_calls: list[dict[str, object]] = []

    await _start_with_selected_question(monkeypatch, row, selection_calls, start_calls)

    assert selection_calls[0]["selection_seed"] == f"friend:{row.id}:5:QUICK_MIX_A1A2"
    assert start_calls[0]["forced_question_id"] == "selected-q"
    assert start_calls[0]["friend_challenge_round"] == 5


@pytest.mark.asyncio
async def test_header_override_returns_none_when_match_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_rounds.TournamentMatchesRepo,
        "get_by_id_for_update",
        async_return(None),
    )

    result = await friend_challenges_rounds._resolve_question_header_override(
        Session(),
        tournament_match_id=challenge().id,
    )

    assert result is None


@pytest.mark.asyncio
async def test_header_override_returns_none_for_non_daily_tournament(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge()
    monkeypatch.setattr(
        friend_challenges_rounds.TournamentMatchesRepo,
        "get_by_id_for_update",
        async_return(SimpleNamespace(tournament_id=row.id)),
    )
    monkeypatch.setattr(
        friend_challenges_rounds.TournamentsRepo,
        "get_by_id",
        async_return(SimpleNamespace(type="PRIVATE")),
    )

    result = await friend_challenges_rounds._resolve_question_header_override(
        Session(),
        tournament_match_id=row.id,
    )

    assert result is None


async def _start_with_selected_question(
    monkeypatch: pytest.MonkeyPatch,
    row,
    selection_calls: list[dict[str, object]],
    start_calls: list[dict[str, object]],
) -> None:
    async def _fake_select_question(_session, mode_code, **kwargs):
        selection_calls.append({"mode_code": mode_code, **kwargs})
        return SimpleNamespace(question_id="selected-q")

    async def _fake_start_session(_session, **kwargs):
        start_calls.append(kwargs)
        return start_result(question_id=str(kwargs["forced_question_id"]))

    monkeypatch.setattr(
        friend_challenges_rounds.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )
    monkeypatch.setattr(
        friend_challenges_rounds_start.QuizSessionsRepo,
        "get_by_friend_challenge_round_user",
        async_return(None),
    )
    monkeypatch.setattr(
        friend_challenges_rounds_start.QuizSessionsRepo,
        "get_by_friend_challenge_round_any_user",
        async_return(None),
    )
    monkeypatch.setattr(
        friend_challenges_rounds_start.QuizSessionsRepo,
        "list_friend_challenge_question_ids_before_round",
        async_return(["old-q"]),
    )
    monkeypatch.setattr(
        "app.game.sessions.service.select_friend_challenge_question",
        _fake_select_question,
    )
    monkeypatch.setattr(friend_challenges_rounds_start, "start_session", _fake_start_session)

    await friend_challenges_rounds.start_friend_challenge_round(
        Session(),
        user_id=11,
        challenge_id=row.id,
        idempotency_key="round:select",
        now_utc=NOW_UTC,
    )
