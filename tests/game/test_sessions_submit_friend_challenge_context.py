from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.db.models.quiz_sessions import QuizSession
from app.game.friend_challenges.constants import DUEL_STATUS_EXPIRED, DUEL_STATUS_LEGACY_ACTIVE
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.service import sessions_submit_friend_challenge_context
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


def _quiz_session(
    *,
    user_id: int = 10,
    source: str = "FRIEND_CHALLENGE",
    friend_challenge_id=None,
    friend_challenge_round: int | None = 2,
) -> QuizSession:
    return QuizSession(
        id=uuid4(),
        user_id=user_id,
        mode_code="QUICK_MIX_A1A2",
        source=source,
        status="STARTED",
        energy_cost_total=0,
        question_id="q-1",
        daily_run_id=None,
        friend_challenge_id=friend_challenge_id,
        friend_challenge_round=friend_challenge_round,
        started_at=NOW_UTC,
        completed_at=None,
        local_date_berlin=date(2026, 3, 15),
        idempotency_key=f"quiz:{uuid4().hex}",
    )


@pytest.mark.asyncio
async def test_load_friend_challenge_answer_state_returns_none_for_non_friend_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_get_by_id_for_update(*args, **kwargs):
        del args, kwargs
        pytest.fail("friend challenge lookup should not run for non-friend sessions")

    monkeypatch.setattr(
        sessions_submit_friend_challenge_context.FriendChallengesRepo,
        "get_by_id_for_update",
        _unexpected_get_by_id_for_update,
    )

    result = await sessions_submit_friend_challenge_context.load_friend_challenge_answer_state(
        _Session(),
        quiz_session=_quiz_session(
            source="MENU", friend_challenge_id=None, friend_challenge_round=None
        ),
        user_id=10,
        now_utc=NOW_UTC,
    )

    assert result is None


@pytest.mark.asyncio
async def test_load_friend_challenge_answer_state_raises_when_challenge_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quiz_session = _quiz_session(friend_challenge_id=uuid4())
    monkeypatch.setattr(
        sessions_submit_friend_challenge_context.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await sessions_submit_friend_challenge_context.load_friend_challenge_answer_state(
            _Session(),
            quiz_session=quiz_session,
            user_id=10,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_load_friend_challenge_answer_state_normalizes_status_and_builds_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(
        status=DUEL_STATUS_LEGACY_ACTIVE,
        creator_user_id=10,
        opponent_user_id=20,
    )
    quiz_session = _quiz_session(friend_challenge_id=challenge.id, friend_challenge_round=3)
    monkeypatch.setattr(
        sessions_submit_friend_challenge_context.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge_context,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    state = await sessions_submit_friend_challenge_context.load_friend_challenge_answer_state(
        _Session(),
        quiz_session=quiz_session,
        user_id=10,
        now_utc=NOW_UTC,
    )

    assert state is not None
    assert state.challenge is challenge
    assert challenge.status == "ACCEPTED"
    assert state.answered_round == 3
    assert state.has_opponent is True
    assert state.is_creator is True


@pytest.mark.asyncio
async def test_load_friend_challenge_answer_state_rejects_outsider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(status="ACCEPTED", creator_user_id=10, opponent_user_id=20)
    quiz_session = _quiz_session(friend_challenge_id=challenge.id)
    monkeypatch.setattr(
        sessions_submit_friend_challenge_context.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge_context,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await sessions_submit_friend_challenge_context.load_friend_challenge_answer_state(
            _Session(),
            quiz_session=quiz_session,
            user_id=999,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_load_friend_challenge_answer_state_emits_expired_event_and_returns_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(status="ACCEPTED", creator_user_id=10, opponent_user_id=20)
    quiz_session = _quiz_session(friend_challenge_id=challenge.id)
    expired_events: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = DUEL_STATUS_EXPIRED
        return True

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        sessions_submit_friend_challenge_context.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge_context,
        "_expire_friend_challenge_if_due",
        _fake_expire,
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge_context,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )

    state = await sessions_submit_friend_challenge_context.load_friend_challenge_answer_state(
        _Session(),
        quiz_session=quiz_session,
        user_id=10,
        now_utc=NOW_UTC,
    )

    assert state is not None
    assert state.challenge.status == DUEL_STATUS_EXPIRED
    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": sessions_submit_friend_challenge_context.EVENT_SOURCE_BOT,
        }
    ]
