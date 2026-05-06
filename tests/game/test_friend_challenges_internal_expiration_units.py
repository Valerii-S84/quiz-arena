from __future__ import annotations

from datetime import timedelta
from typing import cast
from uuid import uuid4

import pytest

from app.game.sessions.service import (
    friend_challenges_analytics,
    friend_challenges_internal_expiration,
)
from tests.game.friend_challenges_unit_support import NOW_UTC, Session, challenge


def test_pending_duel_expires_without_winner() -> None:
    row = challenge(
        status="PENDING", opponent_user_id=None, expires_at=NOW_UTC - timedelta(seconds=1)
    )

    expired = friend_challenges_internal_expiration._expire_friend_challenge_if_due(
        challenge=row,
        now_utc=NOW_UTC,
    )

    assert expired is True
    assert row.status == "EXPIRED"
    assert row.winner_user_id is None
    assert row.completed_at == NOW_UTC


def test_accepted_duel_becomes_creator_walkover_when_only_creator_finished() -> None:
    row = challenge(
        status="ACCEPTED",
        creator_score=4,
        opponent_score=2,
        creator_answered_round=7,
        creator_finished_at=NOW_UTC - timedelta(minutes=1),
        expires_at=NOW_UTC - timedelta(seconds=1),
        total_rounds=7,
    )

    expired = friend_challenges_internal_expiration._expire_friend_challenge_if_due(
        challenge=row,
        now_utc=NOW_UTC,
    )

    assert expired is True
    assert row.status == "WALKOVER"
    assert row.winner_user_id == row.creator_user_id
    assert row.opponent_score == 0
    assert row.completed_at == NOW_UTC


def test_accepted_duel_becomes_scoreless_walkover_when_nobody_finished() -> None:
    row = challenge(
        status="ACCEPTED",
        creator_score=3,
        opponent_score=2,
        expires_at=NOW_UTC - timedelta(seconds=1),
        total_rounds=7,
    )

    expired = friend_challenges_internal_expiration._expire_friend_challenge_if_due(
        challenge=row,
        now_utc=NOW_UTC,
    )

    assert expired is True
    assert row.status == "WALKOVER"
    assert row.winner_user_id is None
    assert row.creator_score == 0
    assert row.opponent_score == 0


@pytest.mark.parametrize(
    ("status", "expires_at"),
    [("COMPLETED", NOW_UTC - timedelta(seconds=1)), ("ACCEPTED", NOW_UTC + timedelta(seconds=1))],
)
def test_expiration_is_noop_when_not_active_or_not_due(status: str, expires_at) -> None:
    row = challenge(status=status, expires_at=expires_at)

    expired = friend_challenges_internal_expiration._expire_friend_challenge_if_due(
        challenge=row,
        now_utc=NOW_UTC,
    )

    assert expired is False
    assert row.status == status
    assert row.completed_at is None


@pytest.mark.asyncio
async def test_expired_event_payload_contains_duel_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    row = challenge(creator_score=2, opponent_score=1)
    events: list[dict[str, object]] = []

    monkeypatch.setattr(
        friend_challenges_analytics,
        "emit_analytics_event",
        _append_kwargs(events),
    )

    await friend_challenges_analytics._emit_friend_challenge_expired_event(
        Session(),
        challenge=row,
        happened_at=NOW_UTC,
        source="bot",
    )

    assert events == [
        {
            "event_type": "duel_expired",
            "source": "bot",
            "happened_at": NOW_UTC,
            "user_id": None,
            "payload": {
                "challenge_id": str(row.id),
                "creator_user_id": 11,
                "opponent_user_id": 22,
                "creator_score": 2,
                "opponent_score": 1,
                "total_rounds": row.total_rounds,
                "expires_at": row.expires_at.isoformat(),
            },
        }
    ]


@pytest.mark.asyncio
async def test_standard_and_rematch_created_events_emit_expected_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(series_id=uuid4(), series_game_number=2, series_best_of=3)
    events: list[dict[str, object]] = []

    monkeypatch.setattr(
        friend_challenges_analytics,
        "emit_analytics_event",
        _append_kwargs(events),
    )

    await friend_challenges_analytics.emit_standard_duel_created_events(
        Session(),
        challenge=row,
        happened_at=NOW_UTC,
        source="bot",
        creator_user_id=11,
        arena_duel_id=uuid4(),
    )
    await friend_challenges_analytics.emit_rematch_duel_created_events(
        Session(),
        rematch=row,
        source_challenge_id=uuid4(),
        opponent_user_id=22,
        happened_at=NOW_UTC,
        source="bot",
        initiator_user_id=11,
    )

    assert len(events) == 3
    assert events[0]["event_type"] == "friend_duel_created"
    first_payload = cast(dict[str, object], events[0]["payload"])
    second_payload = cast(dict[str, object], events[1]["payload"])
    assert "arena_duel_id" in first_payload
    assert second_payload["entrypoint"] == "rematch"
    assert events[2]["event_type"] == "friend_duel_revanche_clicked"


def _append_kwargs(target: list[dict[str, object]]):
    async def _inner(*_args, **kwargs) -> None:
        target.append(kwargs)

    return _inner
