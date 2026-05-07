from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from app.game.sessions.service import (
    friend_challenges_tournament,
    friend_challenges_tournament_progress,
    friend_challenges_tournament_self_bot,
)
from tests.game.friend_challenges_unit_support import NOW_UTC, Session, async_return, challenge


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("challenge_overrides", "match_row", "tournament_row"),
    [
        ({"tournament_match_id": None}, None, None),
        ({"tournament_match_id": uuid4()}, None, None),
        ({"tournament_match_id": uuid4()}, SimpleNamespace(tournament_id=uuid4()), None),
        (
            {"tournament_match_id": uuid4()},
            SimpleNamespace(tournament_id=uuid4()),
            SimpleNamespace(type="PRIVATE"),
        ),
    ],
)
async def test_tournament_progress_short_circuits_when_context_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    challenge_overrides: dict[str, object],
    match_row,
    tournament_row,
) -> None:
    row = challenge(**challenge_overrides)

    monkeypatch.setattr(
        friend_challenges_tournament_progress.TournamentMatchesRepo,
        "get_by_id_for_update",
        async_return(match_row),
    )
    monkeypatch.setattr(
        friend_challenges_tournament_progress.TournamentsRepo,
        "get_by_id",
        async_return(tournament_row),
    )
    monkeypatch.setattr(
        friend_challenges_tournament_progress,
        "handle_daily_cup_tournament_progress",
        _unexpected_daily_progress,
    )

    await friend_challenges_tournament_progress.handle_tournament_duel_progress(
        Session(),
        challenge=row,
        user_id=11,
        now_utc=NOW_UTC,
    )


@pytest.mark.asyncio
async def test_tournament_progress_runs_self_bot_and_daily_cup_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(tournament_match_id=uuid4())
    match = SimpleNamespace(tournament_id=uuid4())
    progress_calls: list[dict[str, object]] = []
    self_bot_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        friend_challenges_tournament_progress.TournamentMatchesRepo,
        "get_by_id_for_update",
        async_return(match),
    )
    monkeypatch.setattr(
        friend_challenges_tournament_progress.TournamentsRepo,
        "get_by_id",
        async_return(SimpleNamespace(type="DAILY_ARENA")),
    )
    monkeypatch.setattr(
        friend_challenges_tournament_progress,
        "is_self_bot_tournament_challenge",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        friend_challenges_tournament_progress,
        "maybe_complete_self_bot_match",
        _append_sync_kwargs(self_bot_calls),
    )
    monkeypatch.setattr(
        friend_challenges_tournament_progress,
        "handle_daily_cup_tournament_progress",
        _append_async_kwargs(progress_calls),
    )

    await friend_challenges_tournament_progress.handle_tournament_duel_progress(
        Session(),
        challenge=row,
        user_id=11,
        now_utc=NOW_UTC,
    )

    assert self_bot_calls[0]["challenge"] is row
    assert progress_calls[0]["tournament_match"] is match
    assert cast(int, progress_calls[0]["grace_minutes"]) >= 1


def test_self_bot_match_auto_completion_sets_bot_score_below_creator() -> None:
    row = challenge(
        tournament_match_id=uuid4(),
        opponent_user_id=11,
        status="CREATOR_DONE",
        total_rounds=7,
        creator_score=5,
    )

    friend_challenges_tournament_self_bot.maybe_complete_self_bot_match(
        challenge=row,
        now_utc=NOW_UTC,
    )

    assert row.status == "COMPLETED"
    assert row.opponent_score == 4
    assert row.winner_user_id == 11
    assert row.opponent_finished_at == NOW_UTC


def test_self_bot_match_fixed_score_can_finish_as_draw() -> None:
    row = challenge(
        tournament_match_id=uuid4(),
        opponent_user_id=11,
        status="CREATOR_DONE",
        total_rounds=7,
        creator_score=4,
    )

    friend_challenges_tournament_self_bot.maybe_complete_self_bot_match(
        challenge=row,
        now_utc=NOW_UTC,
        fixed_bot_score=4,
    )

    assert row.status == "COMPLETED"
    assert row.opponent_score == 4
    assert row.winner_user_id is None


@pytest.mark.asyncio
async def test_create_tournament_match_friend_challenge_uses_round_plan_and_expiry_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = challenge(status="ACCEPTED", total_rounds=5)
    create_calls: list[dict[str, object]] = []
    tournament_match_id = uuid4()
    tournament_id = uuid4()
    expires_at = NOW_UTC + timedelta(hours=2)

    async def _fake_create_row(_session, **kwargs):
        create_calls.append(kwargs)
        created.expires_at = kwargs["now_utc"] + timedelta(hours=1)
        return created

    monkeypatch.setattr(friend_challenges_tournament, "uuid4", lambda: created.id)
    monkeypatch.setattr(friend_challenges_tournament, "resolve_tournament_rounds", lambda **_: 5)
    monkeypatch.setattr(
        friend_challenges_tournament,
        "select_duel_question_ids",
        async_return(["q-1", "q-2", "q-3", "q-4", "q-5"]),
    )
    monkeypatch.setattr(
        friend_challenges_tournament,
        "_create_friend_challenge_row",
        _fake_create_row,
    )

    snapshot = await friend_challenges_tournament.create_tournament_match_friend_challenge(
        Session(),
        creator_user_id=11,
        opponent_user_id=22,
        tournament_id=tournament_id,
        tournament_round_no=3,
        mode_code="QUICK_MIX_A1A2",
        total_rounds=5,
        tournament_match_id=tournament_match_id,
        now_utc=NOW_UTC,
        expires_at=expires_at,
    )

    assert snapshot.challenge_id == created.id
    assert snapshot.tournament_match_id == tournament_match_id
    assert created.expires_at == expires_at
    assert create_calls[0]["question_ids"] == ["q-1", "q-2", "q-3", "q-4", "q-5"]


async def _unexpected_daily_progress(*_args, **_kwargs):
    pytest.fail("daily cup progress should not run")


def _append_sync_kwargs(target: list[dict[str, object]]):
    def _inner(*_args, **kwargs) -> None:
        target.append(kwargs)

    return _inner


def _append_async_kwargs(target: list[dict[str, object]]):
    async def _inner(*_args, **kwargs) -> None:
        target.append(kwargs)

    return _inner
