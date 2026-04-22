from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.game.sessions.service import friend_challenges_internal_expiration
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _challenge(**overrides: object):
    payload: dict[str, object] = {
        "creator_user_id": 101,
        "opponent_user_id": 202,
        "status": "ACCEPTED",
        "total_rounds": 5,
        "creator_score": 3,
        "opponent_score": 2,
        "creator_answered_round": 0,
        "opponent_answered_round": 0,
        "expires_at": NOW_UTC - timedelta(minutes=1),
    }
    payload.update(overrides)
    return build_friend_challenge(**payload)


def test_friend_challenge_expires_at_delegates_to_records_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected = NOW_UTC + timedelta(minutes=5)

    def _fake_friend_challenge_expires_at(*, now_utc: datetime) -> datetime:
        captured_kwargs["now_utc"] = now_utc
        return expected

    monkeypatch.setattr(
        friend_challenges_internal_expiration,
        "friend_challenge_expires_at",
        _fake_friend_challenge_expires_at,
    )

    result = friend_challenges_internal_expiration._friend_challenge_expires_at(now_utc=NOW_UTC)

    assert result is expected
    assert captured_kwargs == {"now_utc": NOW_UTC}


def test_friend_challenge_expires_at_accepted_delegates_to_records_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected = NOW_UTC + timedelta(minutes=10)

    def _fake_friend_challenge_expires_at_accepted(*, now_utc: datetime) -> datetime:
        captured_kwargs["now_utc"] = now_utc
        return expected

    monkeypatch.setattr(
        friend_challenges_internal_expiration,
        "friend_challenge_expires_at_accepted",
        _fake_friend_challenge_expires_at_accepted,
    )

    result = friend_challenges_internal_expiration._friend_challenge_expires_at_accepted(
        now_utc=NOW_UTC
    )

    assert result is expected
    assert captured_kwargs == {"now_utc": NOW_UTC}


def test_expire_friend_challenge_if_due_delegates_to_expiry_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    captured_kwargs: dict[str, object] = {}

    def _fake_expire_friend_challenge_if_due(*, challenge, now_utc: datetime) -> bool:
        captured_kwargs["challenge"] = challenge
        captured_kwargs["now_utc"] = now_utc
        return True

    monkeypatch.setattr(
        friend_challenges_internal_expiration,
        "expire_friend_challenge_if_due",
        _fake_expire_friend_challenge_if_due,
    )

    result = friend_challenges_internal_expiration._expire_friend_challenge_if_due(
        challenge=challenge,
        now_utc=NOW_UTC,
    )

    assert result is True
    assert captured_kwargs == {
        "challenge": challenge,
        "now_utc": NOW_UTC,
    }


@pytest.mark.asyncio
async def test_emit_friend_challenge_expired_event_delegates_to_expiry_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    captured_kwargs: dict[str, object] = {}
    session = _Session()

    async def _fake_emit_friend_challenge_expired_event(session, **kwargs) -> None:
        captured_kwargs["session"] = session
        captured_kwargs.update(kwargs)

    monkeypatch.setattr(
        friend_challenges_internal_expiration,
        "emit_friend_challenge_expired_event",
        _fake_emit_friend_challenge_expired_event,
    )

    await friend_challenges_internal_expiration._emit_friend_challenge_expired_event(
        session,
        challenge=challenge,
        happened_at=NOW_UTC,
        source="BOT",
    )

    assert captured_kwargs == {
        "session": session,
        "challenge": challenge,
        "happened_at": NOW_UTC,
        "source": "BOT",
    }
