from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import ArenaActiveDuelRow, ArenaDuelsRepo
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_BASELINE,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_DUEL_STATUS_EXPIRED,
)
from app.game.friend_challenges.constants import (
    DUEL_STATUS_CANCELED,
    DUEL_STATUS_COMPLETED,
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_EXPIRED,
    DUEL_STATUS_WALKOVER,
    DUEL_TYPE_DIRECT,
    DUEL_TYPE_OPEN,
)
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeArenaPublishBaselineRequiredError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.service import friend_challenges_manage
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    async def flush(self, objects: Sequence[Any] | None = None) -> None:
        del objects
        pass


def _challenge(
    *,
    status: str = DUEL_STATUS_EXPIRED,
    creator_user_id: int = 11,
    opponent_user_id: int | None = 22,
    challenge_type: str = DUEL_TYPE_DIRECT,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        challenge_type=challenge_type,
        status=status,
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        question_ids=[f"duel-q-{index}" for index in range(1, 8)],
        tournament_match_id=None,
        total_rounds=7,
        creator_score=6,
        creator_answered_round=7,
        creator_finished_at=NOW_UTC,
        completed_at=None,
        updated_at=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "func",
    [
        friend_challenges_manage.repost_friend_challenge_as_open,
        friend_challenges_manage.cancel_friend_challenge_by_creator,
    ],
)
async def test_manage_friend_challenge_raises_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
    func,
) -> None:
    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await func(
            _Session(),
            user_id=11,
            challenge_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func", "challenge", "user_id"),
    [
        (
            friend_challenges_manage.repost_friend_challenge_as_open,
            _challenge(creator_user_id=11),
            999,
        ),
        (
            friend_challenges_manage.cancel_friend_challenge_by_creator,
            _challenge(status="ACCEPTED", creator_user_id=11),
            11,
        ),
    ],
)
async def test_manage_friend_challenge_rejects_access_checks(
    monkeypatch: pytest.MonkeyPatch,
    func,
    challenge: SimpleNamespace,
    user_id: int,
) -> None:
    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await func(
            _Session(),
            user_id=user_id,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_repost_friend_challenge_as_open_creates_repost_without_legacy_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(status="ACTIVE", creator_user_id=11, opponent_user_id=None)
    repost = SimpleNamespace(challenge_id=uuid4(), total_rounds=challenge.total_rounds)
    expired_events: list[dict[str, object]] = []
    analytics_events: list[dict[str, object]] = []
    create_calls: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = DUEL_STATUS_EXPIRED
        return True

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    async def _fake_create_friend_challenge(*_args, **kwargs):
        create_calls.append(kwargs)
        return repost

    async def _fake_emit_analytics_event(*_args, **kwargs) -> None:
        analytics_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        _fake_expire,
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "create_friend_challenge",
        _fake_create_friend_challenge,
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )

    result = await friend_challenges_manage.repost_friend_challenge_as_open(
        _Session(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result is repost
    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_manage.EVENT_SOURCE_BOT,
        }
    ]
    assert create_calls == [
        {
            "creator_user_id": 11,
            "mode_code": challenge.mode_code,
            "now_utc": NOW_UTC,
            "challenge_type": friend_challenges_manage.DUEL_TYPE_OPEN,
            "total_rounds": challenge.total_rounds,
        }
    ]
    assert analytics_events == []


@pytest.mark.asyncio
async def test_repost_friend_challenge_as_open_rejects_non_expired_creator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(status="ACCEPTED", creator_user_id=11)

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_manage.repost_friend_challenge_as_open(
            _Session(),
            user_id=11,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_cancel_friend_challenge_by_creator_marks_canceled_and_returns_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    analytics_events: list[dict[str, object]] = []
    snapshot = {"challenge_id": str(challenge.id), "status": DUEL_STATUS_CANCELED}

    async def _fake_emit_analytics_event(*_args, **kwargs) -> None:
        analytics_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: snapshot if challenge_row is challenge else None,
    )

    result = await friend_challenges_manage.cancel_friend_challenge_by_creator(
        _Session(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == snapshot
    assert challenge.status == DUEL_STATUS_CANCELED
    assert challenge.completed_at == NOW_UTC
    assert challenge.updated_at == NOW_UTC
    assert analytics_events == [
        {
            "event_type": "duel_canceled_by_creator",
            "source": friend_challenges_manage.EVENT_SOURCE_BOT,
            "happened_at": NOW_UTC,
            "user_id": 11,
            "payload": {
                "challenge_id": str(challenge.id),
                "format": challenge.total_rounds,
            },
        }
    ]


@pytest.mark.asyncio
async def test_cancel_friend_challenge_by_creator_allows_pending_unjoined_duel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(
        status="PENDING",
        creator_user_id=11,
        opponent_user_id=None,
    )

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "emit_analytics_event",
        _async_return(None),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: challenge_row,
    )

    result = await friend_challenges_manage.cancel_friend_challenge_by_creator(
        _Session(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result is challenge
    assert challenge.status == DUEL_STATUS_CANCELED
    assert challenge.completed_at == NOW_UTC


@pytest.mark.asyncio
async def test_cancel_friend_challenge_by_creator_emits_expired_event_before_access_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(status="ACTIVE", creator_user_id=11, opponent_user_id=None)
    expired_events: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = DUEL_STATUS_EXPIRED
        return True

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(friend_challenges_manage, "_expire_friend_challenge_if_due", _fake_expire)
    monkeypatch.setattr(
        friend_challenges_manage,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_manage.cancel_friend_challenge_by_creator(
            _Session(),
            user_id=999,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )

    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_manage.EVENT_SOURCE_BOT,
        }
    ]


@pytest.mark.asyncio
async def test_publish_friend_challenge_to_arena_creates_active_duel_from_creator_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(
        status=DUEL_STATUS_CREATOR_DONE,
        creator_user_id=11,
        opponent_user_id=None,
    )
    created: dict[str, object] = {}

    async def _fake_create_duel(*_args, **kwargs):
        created["duel"] = kwargs["duel"]
        return kwargs["duel"]

    async def _fake_create_attempt(*_args, **kwargs):
        created["attempt"] = kwargs["attempt"]
        return kwargs["attempt"]

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        ArenaDuelsRepo,
        "get_source_friend_duel_with_baseline_for_update",
        _async_return(None),
    )
    monkeypatch.setattr(ArenaDuelsRepo, "create_duel", _fake_create_duel)
    monkeypatch.setattr(
        ArenaDuelsRepo,
        "create_attempt",
        _fake_create_attempt,
    )
    monkeypatch.setattr(
        friend_challenges_manage.QuizSessionsRepo,
        "sum_completed_duration_ms_for_friend_challenge_user",
        _async_return(48_000),
    )

    result = await friend_challenges_manage.publish_friend_challenge_to_arena(
        _Session(),
        user_id=11,
        friend_challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    duel = cast(ArenaDuel, created["duel"])
    attempt = cast(ArenaAttempt, created["attempt"])
    assert duel.status == "ACTIVE"
    assert duel.source_friend_challenge_id == challenge.id
    assert duel.question_ids == challenge.question_ids
    assert duel.baseline_attempt_id == attempt.id
    assert attempt.score == 6
    assert attempt.time_ms == 48_000
    assert attempt.completed_at == NOW_UTC
    assert result.baseline_score == 6
    assert result.baseline_time_ms == 48_000


@pytest.mark.asyncio
async def test_publish_friend_challenge_to_arena_requests_baseline_for_empty_friend_duel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(status="PENDING", creator_user_id=11, opponent_user_id=None)
    challenge.creator_answered_round = 0
    challenge.creator_finished_at = None

    async def _unexpected_create_duel(*_args, **_kwargs):
        pytest.fail("empty friend-duel must not create an Arena duel")

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        ArenaDuelsRepo,
        "create_duel",
        _unexpected_create_duel,
    )

    with pytest.raises(FriendChallengeArenaPublishBaselineRequiredError):
        await friend_challenges_manage.publish_friend_challenge_to_arena(
            _Session(),
            user_id=11,
            friend_challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_publish_friend_challenge_to_arena_returns_existing_active_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(
        status=DUEL_STATUS_CREATOR_DONE,
        creator_user_id=11,
        opponent_user_id=None,
    )
    existing_duel = _arena_duel_from_friend(challenge_id=challenge.id)
    existing_attempt = _arena_baseline_attempt(duel_id=existing_duel.id)
    existing_duel.baseline_attempt_id = existing_attempt.id

    async def _unexpected_create_duel(*_args, **_kwargs):
        pytest.fail("duplicate friend publish must not create another Arena duel")

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        ArenaDuelsRepo,
        "get_source_friend_duel_with_baseline_for_update",
        _async_return(ArenaActiveDuelRow(existing_duel, existing_attempt)),
    )
    monkeypatch.setattr(ArenaDuelsRepo, "create_duel", _unexpected_create_duel)

    result = await friend_challenges_manage.publish_friend_challenge_to_arena(
        _Session(),
        user_id=11,
        friend_challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result.duel_id == existing_duel.id
    assert result.baseline_attempt_id == existing_attempt.id
    assert result.baseline_score == existing_attempt.score
    assert result.baseline_time_ms == existing_attempt.time_ms


@pytest.mark.asyncio
async def test_publish_friend_challenge_to_arena_rejects_expired_duplicate_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(
        status=DUEL_STATUS_CREATOR_DONE,
        creator_user_id=11,
        opponent_user_id=None,
    )
    existing_duel = _arena_duel_from_friend(
        challenge_id=challenge.id,
        status=ARENA_DUEL_STATUS_EXPIRED,
    )
    existing_attempt = _arena_baseline_attempt(duel_id=existing_duel.id)
    existing_duel.baseline_attempt_id = existing_attempt.id

    async def _unexpected_create_duel(*_args, **_kwargs):
        pytest.fail("expired duplicate publish must be denied, not recreated")

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        ArenaDuelsRepo,
        "get_source_friend_duel_with_baseline_for_update",
        _async_return(ArenaActiveDuelRow(existing_duel, existing_attempt)),
    )
    monkeypatch.setattr(ArenaDuelsRepo, "create_duel", _unexpected_create_duel)

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_manage.publish_friend_challenge_to_arena(
            _Session(),
            user_id=11,
            friend_challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "challenge",
    [
        _challenge(
            status=DUEL_STATUS_CREATOR_DONE,
            creator_user_id=11,
            opponent_user_id=22,
        ),
        _challenge(
            status=DUEL_STATUS_COMPLETED,
            creator_user_id=11,
            opponent_user_id=None,
        ),
        _challenge(
            status=DUEL_STATUS_WALKOVER,
            creator_user_id=11,
            opponent_user_id=None,
        ),
        _challenge(
            status=DUEL_STATUS_CREATOR_DONE,
            creator_user_id=11,
            opponent_user_id=None,
            challenge_type=DUEL_TYPE_OPEN,
        ),
    ],
)
async def test_publish_friend_challenge_to_arena_rejects_unclean_server_state(
    monkeypatch: pytest.MonkeyPatch,
    challenge: SimpleNamespace,
) -> None:
    async def _unexpected_source_lookup(*_args, **_kwargs):
        pytest.fail("unclean friend-duel state must not reach Arena lookup")

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        ArenaDuelsRepo,
        "get_source_friend_duel_with_baseline_for_update",
        _unexpected_source_lookup,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_manage.publish_friend_challenge_to_arena(
            _Session(),
            user_id=11,
            friend_challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _arena_duel_from_friend(
    *,
    challenge_id,
    status: str = ARENA_DUEL_STATUS_ACTIVE,
) -> ArenaDuel:
    return ArenaDuel(
        id=uuid4(),
        creator_user_id=11,
        baseline_attempt_id=None,
        question_ids=[f"duel-q-{index}" for index in range(1, 8)],
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        status=status,
        expires_at=NOW_UTC.replace(hour=13),
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
        source_friend_challenge_id=challenge_id,
    )


def _arena_baseline_attempt(*, duel_id) -> ArenaAttempt:
    return ArenaAttempt(
        id=uuid4(),
        arena_duel_id=duel_id,
        user_id=11,
        role=ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
        access_type="FREE",
        score=6,
        time_ms=48_000,
        result=ARENA_ATTEMPT_RESULT_BASELINE,
        completed_at=NOW_UTC,
        created_at=NOW_UTC,
    )
