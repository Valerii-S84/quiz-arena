from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.game.sessions.service import friend_challenges_round_start_headers
from app.game.sessions.types import SessionQuestionView, StartSessionResult
from app.game.tournaments.constants import TOURNAMENT_TYPE_DAILY_ARENA
from tests.type_helpers import AsyncSessionStub

TOURNAMENT_MATCH_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TOURNAMENT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


def _start_result() -> StartSessionResult:
    return StartSessionResult(
        session=SessionQuestionView(
            session_id=uuid4(),
            question_id="question-1",
            text="Question",
            options=("A", "B", "C", "D"),
            mode_code="QUICK_MIX_A1A2",
            source="FRIEND_CHALLENGE",
        ),
        energy_free=0,
        energy_paid=0,
        idempotent_replay=False,
    )


@pytest.mark.asyncio
async def test_resolve_round_header_override_returns_none_without_match_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_get_match(*args, **kwargs):
        del args, kwargs
        pytest.fail("tournament match lookup should not run without a tournament match id")

    monkeypatch.setattr(
        friend_challenges_round_start_headers.TournamentMatchesRepo,
        "get_by_id_for_update",
        _unexpected_get_match,
    )

    header_override = (
        await friend_challenges_round_start_headers.resolve_friend_challenge_round_header_override(
            _Session(),
            tournament_match_id=None,
        )
    )

    assert header_override is None


@pytest.mark.asyncio
async def test_resolve_round_header_override_returns_none_when_match_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_get_tournament(*args, **kwargs):
        del args, kwargs
        pytest.fail("tournament lookup should not run when the match is missing")

    monkeypatch.setattr(
        friend_challenges_round_start_headers.TournamentMatchesRepo,
        "get_by_id_for_update",
        _async_return(None),
    )
    monkeypatch.setattr(
        friend_challenges_round_start_headers.TournamentsRepo,
        "get_by_id",
        _unexpected_get_tournament,
    )

    header_override = (
        await friend_challenges_round_start_headers.resolve_friend_challenge_round_header_override(
            _Session(),
            tournament_match_id=TOURNAMENT_MATCH_ID,
        )
    )

    assert header_override is None


@pytest.mark.asyncio
async def test_resolve_round_header_override_returns_none_for_non_daily_tournament(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_round_start_headers.TournamentMatchesRepo,
        "get_by_id_for_update",
        _async_return(SimpleNamespace(tournament_id=TOURNAMENT_ID)),
    )
    monkeypatch.setattr(
        friend_challenges_round_start_headers.TournamentsRepo,
        "get_by_id",
        _async_return(SimpleNamespace(type="PRIVATE")),
    )

    header_override = (
        await friend_challenges_round_start_headers.resolve_friend_challenge_round_header_override(
            _Session(),
            tournament_match_id=TOURNAMENT_MATCH_ID,
        )
    )

    assert header_override is None


@pytest.mark.asyncio
async def test_apply_round_header_override_sets_daily_arena_cup_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start_result = _start_result()

    monkeypatch.setattr(
        friend_challenges_round_start_headers.TournamentMatchesRepo,
        "get_by_id_for_update",
        _async_return(SimpleNamespace(tournament_id=TOURNAMENT_ID)),
    )
    monkeypatch.setattr(
        friend_challenges_round_start_headers.TournamentsRepo,
        "get_by_id",
        _async_return(SimpleNamespace(type=TOURNAMENT_TYPE_DAILY_ARENA)),
    )

    await friend_challenges_round_start_headers.apply_friend_challenge_round_header_override(
        _Session(),
        start_result=start_result,
        tournament_match_id=TOURNAMENT_MATCH_ID,
    )

    assert start_result.session.header_mode_label_override == "Daily Arena Cup"
