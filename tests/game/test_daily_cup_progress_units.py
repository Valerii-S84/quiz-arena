from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from app.game.sessions.service import friend_challenges_tournament_daily_cup

NOW_UTC = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_daily_cup_progress_returns_early_when_duel_not_finished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge: Any = SimpleNamespace(status="ACCEPTED")
    tournament_match: Any = SimpleNamespace(status="PENDING", deadline=NOW_UTC + timedelta(hours=1))

    async def _unexpected_settle(*_args, **_kwargs):
        pytest.fail("unfinished duel must not settle the match")

    monkeypatch.setattr(
        "app.game.tournaments.settlement.settle_pending_match_from_duel",
        _unexpected_settle,
    )

    await friend_challenges_tournament_daily_cup.handle_daily_cup_tournament_progress(
        cast(Any, SimpleNamespace()),
        challenge=challenge,
        user_id=11,
        now_utc=NOW_UTC,
        tournament_match=tournament_match,
        tournament=cast(
            Any,
            SimpleNamespace(current_round=1, registration_deadline=NOW_UTC, round_start_time=None),
        ),
        grace_minutes=15,
    )


@pytest.mark.asyncio
async def test_daily_cup_progress_stops_when_match_was_not_settled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge: Any = SimpleNamespace(
        status="COMPLETED",
        opponent_user_id=22,
        creator_score=5,
        opponent_score=4,
    )
    tournament_match: Any = SimpleNamespace(
        tournament_id=uuid4(),
        round_no=1,
        user_a=11,
        user_b=22,
        status="PENDING",
        deadline=NOW_UTC + timedelta(hours=1),
    )

    monkeypatch.setattr(
        "app.game.tournaments.settlement.settle_pending_match_from_duel",
        _async_return(False),
    )
    monkeypatch.setattr(
        "app.game.tournaments.lifecycle.check_and_advance_round",
        _unexpected_async,
    )

    await friend_challenges_tournament_daily_cup.handle_daily_cup_tournament_progress(
        cast(Any, SimpleNamespace()),
        challenge=challenge,
        user_id=11,
        now_utc=NOW_UTC,
        tournament_match=tournament_match,
        tournament=cast(
            Any,
            SimpleNamespace(current_round=1, registration_deadline=NOW_UTC, round_start_time=None),
        ),
        grace_minutes=15,
    )


@pytest.mark.asyncio
async def test_daily_cup_progress_emits_events_and_messages_after_settlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []
    round_messages: list[dict[str, object]] = []
    result_messages: list[dict[str, object]] = []
    challenge: Any = SimpleNamespace(
        status="COMPLETED",
        opponent_user_id=22,
        creator_score=5,
        opponent_score=4,
    )
    tournament_match: Any = SimpleNamespace(
        tournament_id=uuid4(),
        round_no=1,
        user_a=11,
        user_b=22,
        status="PENDING",
        deadline=NOW_UTC + timedelta(hours=1),
    )
    tournament: Any = SimpleNamespace(
        current_round=2,
        registration_deadline=NOW_UTC + timedelta(days=1),
        round_start_time=NOW_UTC + timedelta(hours=2),
    )

    monkeypatch.setattr(
        "app.game.tournaments.settlement.settle_pending_match_from_duel",
        _async_return(True),
    )
    monkeypatch.setattr(
        "app.game.tournaments.lifecycle.check_and_advance_round",
        _async_return({"round_started": 1, "tournament_completed": 1}),
    )
    monkeypatch.setattr(
        friend_challenges_tournament_daily_cup,
        "emit_analytics_event",
        _append_async_kwargs(events),
    )
    monkeypatch.setattr(
        "app.workers.tasks.daily_cup_messaging.enqueue_daily_cup_round_messaging",
        _append_sync_kwargs(round_messages),
    )
    monkeypatch.setattr(
        friend_challenges_tournament_daily_cup.TournamentParticipantsRepo,
        "count_for_tournament",
        _async_return(16),
    )
    monkeypatch.setattr(
        "app.workers.tasks.daily_cup_match_results.send_daily_cup_match_result_messages",
        _append_async_kwargs(result_messages),
    )

    await friend_challenges_tournament_daily_cup.handle_daily_cup_tournament_progress(
        cast(Any, SimpleNamespace()),
        challenge=challenge,
        user_id=11,
        now_utc=NOW_UTC,
        tournament_match=tournament_match,
        tournament=tournament,
        grace_minutes=15,
    )

    assert {event["event_type"] for event in events} == {
        "daily_cup_match_completed",
        "daily_cup_round_started",
    }
    assert round_messages == [
        {
            "tournament_id": str(tournament_match.tournament_id),
            "enqueue_completion_followups": True,
        }
    ]
    assert cast(int, result_messages[0]["rounds_total"]) >= 1
    assert result_messages[0]["next_round_start_time"] == tournament.round_start_time


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


async def _unexpected_async(*_args, **_kwargs):
    pytest.fail("unexpected async call")


def _append_sync_kwargs(target: list[dict[str, object]]):
    def _inner(*_args, **kwargs) -> None:
        target.append(kwargs)

    return _inner


def _append_async_kwargs(target: list[dict[str, object]]):
    async def _inner(*_args, **kwargs) -> None:
        target.append(kwargs)

    return _inner
