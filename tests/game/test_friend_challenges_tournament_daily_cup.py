from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournaments import Tournament
from app.game.sessions.service import friend_challenges_tournament_daily_cup
from app.game.tournaments.constants import TOURNAMENT_MATCH_STATUS_PENDING
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


def _tournament(**overrides: object) -> Tournament:
    payload: dict[str, object] = {
        "id": uuid4(),
        "type": "DAILY_ARENA",
        "created_by": None,
        "name": "Daily Cup",
        "status": "ROUND_2",
        "format": "QUICK_5",
        "max_participants": 8,
        "current_round": 2,
        "registration_deadline": NOW_UTC - timedelta(hours=2),
        "round_deadline": NOW_UTC + timedelta(minutes=30),
        "round_start_time": NOW_UTC + timedelta(minutes=45),
        "bracket": None,
        "invite_code": "daily-cup",
        "created_at": NOW_UTC - timedelta(days=1),
    }
    payload.update(overrides)
    return Tournament(**payload)


def _tournament_match(*, tournament_id, **overrides: object) -> TournamentMatch:
    payload: dict[str, object] = {
        "id": uuid4(),
        "tournament_id": tournament_id,
        "round_no": 2,
        "round_number": 2,
        "user_a": 10,
        "user_b": 20,
        "bracket_slot_a": None,
        "bracket_slot_b": None,
        "friend_challenge_id": None,
        "match_timeout_task_id": None,
        "player_a_finished_at": None,
        "player_b_finished_at": None,
        "status": TOURNAMENT_MATCH_STATUS_PENDING,
        "winner_id": None,
        "deadline": NOW_UTC + timedelta(minutes=30),
    }
    payload.update(overrides)
    return TournamentMatch(**payload)


@pytest.mark.asyncio
async def test_handle_daily_cup_tournament_progress_tightens_pending_deadline() -> None:
    challenge = build_friend_challenge(status="CREATOR_DONE")
    tournament = _tournament(round_deadline=NOW_UTC + timedelta(minutes=25))
    tournament_match = _tournament_match(
        tournament_id=tournament.id,
        deadline=NOW_UTC + timedelta(minutes=40),
    )

    await friend_challenges_tournament_daily_cup.handle_daily_cup_tournament_progress(
        _Session(),
        challenge=challenge,
        user_id=10,
        now_utc=NOW_UTC,
        tournament_match=tournament_match,
        tournament=tournament,
        grace_minutes=15,
    )

    expected_deadline = NOW_UTC + timedelta(minutes=15)
    assert tournament_match.deadline == expected_deadline
    assert tournament.round_deadline == expected_deadline


@pytest.mark.asyncio
async def test_handle_daily_cup_tournament_progress_stops_when_settlement_does_not_change_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(status="COMPLETED")
    tournament = _tournament()
    tournament_match = _tournament_match(tournament_id=tournament.id)

    async def _unexpected_emit(*args, **kwargs):
        del args, kwargs
        pytest.fail("analytics should not emit when the duel settlement did not change the match")

    monkeypatch.setattr(
        friend_challenges_tournament_daily_cup,
        "emit_analytics_event",
        _unexpected_emit,
    )
    monkeypatch.setattr(
        friend_challenges_tournament_daily_cup,
        "_settle_daily_cup_match_and_advance_round",
        _async_return(None),
    )

    await friend_challenges_tournament_daily_cup.handle_daily_cup_tournament_progress(
        _Session(),
        challenge=challenge,
        user_id=10,
        now_utc=NOW_UTC,
        tournament_match=tournament_match,
        tournament=tournament,
        grace_minutes=15,
    )


@pytest.mark.asyncio
async def test_handle_daily_cup_tournament_progress_emits_events_and_sends_match_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(
        status="COMPLETED",
        creator_user_id=10,
        opponent_user_id=20,
        creator_score=4,
        opponent_score=3,
    )
    tournament = _tournament(current_round=3)
    tournament_match = _tournament_match(
        tournament_id=tournament.id,
        round_no=2,
        user_a=10,
        user_b=20,
    )
    analytics_calls: list[dict[str, object]] = []
    completion_calls: list[dict[str, object]] = []
    result_calls: list[dict[str, object]] = []

    async def _fake_emit_analytics_event(_session, **kwargs):
        analytics_calls.append(kwargs)

    async def _fake_send_daily_cup_match_result_messages(_session, **kwargs):
        result_calls.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_tournament_daily_cup,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )
    monkeypatch.setattr(
        friend_challenges_tournament_daily_cup,
        "_settle_daily_cup_match_and_advance_round",
        _async_return(
            {
                "matches_settled": 1,
                "matches_created": 0,
                "round_started": 1,
                "tournament_completed": 1,
            }
        ),
    )
    monkeypatch.setattr(
        friend_challenges_tournament_daily_cup.TournamentParticipantsRepo,
        "count_for_tournament",
        _async_return(8),
    )
    monkeypatch.setattr(
        "app.workers.tasks.daily_cup_match_results.send_daily_cup_match_result_messages",
        _fake_send_daily_cup_match_result_messages,
    )
    monkeypatch.setattr(
        "app.workers.tasks.daily_cup_messaging.enqueue_daily_cup_round_messaging",
        lambda **kwargs: completion_calls.append(kwargs),
    )

    await friend_challenges_tournament_daily_cup.handle_daily_cup_tournament_progress(
        _Session(),
        challenge=challenge,
        user_id=10,
        now_utc=NOW_UTC,
        tournament_match=tournament_match,
        tournament=tournament,
        grace_minutes=15,
    )

    assert analytics_calls == [
        {
            "event_type": "daily_cup_match_completed",
            "source": friend_challenges_tournament_daily_cup.EVENT_SOURCE_BOT,
            "happened_at": NOW_UTC,
            "user_id": 10,
            "payload": {
                "tournament_id": str(tournament.id),
                "round_no": 2,
            },
        },
        {
            "event_type": "daily_cup_round_started",
            "source": friend_challenges_tournament_daily_cup.EVENT_SOURCE_BOT,
            "happened_at": NOW_UTC,
            "user_id": 10,
            "payload": {
                "tournament_id": str(tournament.id),
                "round_no": 3,
            },
        },
    ]
    assert completion_calls == [
        {
            "tournament_id": str(tournament.id),
            "enqueue_completion_followups": True,
        }
    ]
    assert result_calls == [
        {
            "tournament_id": tournament.id,
            "round_no": 2,
            "user_a": 10,
            "user_b": 20,
            "user_a_points": 4,
            "user_b_points": 3,
            "rounds_total": (
                friend_challenges_tournament_daily_cup.daily_cup_max_rounds_for_participants(
                    participants_total=8
                )
            ),
            "tournament_registration_deadline": tournament.registration_deadline,
            "next_round_start_time": tournament.round_start_time,
        }
    ]
