from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from app.game.arena_duels import revanche
from app.game.arena_duels.constants import (
    ARENA_REVANCHE_NOTIFICATION_TYPE,
    ARENA_REVANCHE_REQUESTED_EVENT,
    ARENA_REVANCHE_SENT_EVENT,
)
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
DUEL_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SOURCE_ATTEMPT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
CHALLENGE_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _context() -> revanche.ArenaRevancheContext:
    return revanche.ArenaRevancheContext(
        arena_duel_id=DUEL_ID,
        source_attempt_id=SOURCE_ATTEMPT_ID,
        sender_user_id=11,
        receiver_user_id=22,
        mode_code="QUICK_MIX_A1A2",
    )


@pytest.mark.asyncio
async def test_duplicate_revanche_send_is_deduped(monkeypatch: pytest.MonkeyPatch) -> None:
    lock_calls: list[dict[str, object]] = []
    monkeypatch.setattr(revanche, "load_arena_revanche_context", _async_return(_context()))
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "lock_arena_revanche_sender_quota",
        _append_kwargs([]),
    )
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "lock_arena_revanche_event_key",
        _append_kwargs(lock_calls),
    )
    monkeypatch.setattr(revanche.AnalyticsRepo, "has_arena_revanche_event", _async_return(True))
    monkeypatch.setattr(
        revanche.DuelLimitService,
        "resolve_revanche_access_type",
        _fail("duplicate request must not consume quota"),
    )
    monkeypatch.setattr(
        revanche,
        "create_revanche_friend_challenge",
        _fail("duplicate request must not create another challenge"),
    )

    request = await _prepare_request()

    assert request.already_sent is True
    assert request.challenge is None
    payload = cast(dict[str, object], lock_calls[0]["payload"])
    assert payload["notification_type"] == ARENA_REVANCHE_NOTIFICATION_TYPE


@pytest.mark.asyncio
async def test_revanche_retry_reuses_pending_request_without_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(revanche, "load_arena_revanche_context", _async_return(_context()))
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "lock_arena_revanche_sender_quota",
        _append_kwargs([]),
    )
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "lock_arena_revanche_event_key",
        _append_kwargs([]),
    )
    monkeypatch.setattr(revanche.AnalyticsRepo, "has_arena_revanche_event", _async_return(False))
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "get_arena_revanche_event_payload",
        _async_return({"challenge_id": str(CHALLENGE_ID)}),
    )
    monkeypatch.setattr(
        revanche,
        "load_revanche_friend_challenge",
        _async_return(SimpleNamespace(challenge_id=CHALLENGE_ID)),
    )
    monkeypatch.setattr(
        revanche.DuelLimitService,
        "resolve_revanche_access_type",
        _fail("pending retry must not consume quota"),
    )
    monkeypatch.setattr(
        revanche,
        "create_revanche_friend_challenge",
        _fail("pending retry must not create another challenge"),
    )

    request = await _prepare_request()

    assert request.already_sent is False
    assert request.challenge is not None
    assert request.challenge.challenge_id == CHALLENGE_ID


@pytest.mark.asyncio
async def test_new_revanche_records_requested_not_sent_before_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_calls: list[dict[str, object]] = []
    monkeypatch.setattr(revanche, "load_arena_revanche_context", _async_return(_context()))
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "lock_arena_revanche_sender_quota",
        _append_kwargs([]),
    )
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "lock_arena_revanche_event_key",
        _append_kwargs([]),
    )
    monkeypatch.setattr(revanche.AnalyticsRepo, "has_arena_revanche_event", _async_return(False))
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "get_arena_revanche_event_payload",
        _async_return(None),
    )
    monkeypatch.setattr(
        revanche.DuelLimitService,
        "resolve_revanche_access_type",
        _async_return("FREE"),
    )
    monkeypatch.setattr(
        revanche,
        "create_revanche_friend_challenge",
        _async_return(SimpleNamespace(challenge_id=CHALLENGE_ID)),
    )
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "create_arena_revanche_event_once",
        _append_kwargs_and_return(event_calls, True),
    )

    request = await _prepare_request()

    assert request.challenge is not None
    assert event_calls[0]["event_type"] == ARENA_REVANCHE_REQUESTED_EVENT
    assert event_calls[0]["event_type"] != ARENA_REVANCHE_SENT_EVENT


@pytest.mark.asyncio
async def test_new_revanche_locks_sender_quota_before_access_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(revanche, "load_arena_revanche_context", _async_return(_context()))
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "lock_arena_revanche_sender_quota",
        _append_label(calls, "sender_quota_lock"),
    )
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "lock_arena_revanche_event_key",
        _append_label(calls, "event_lock"),
    )
    monkeypatch.setattr(revanche.AnalyticsRepo, "has_arena_revanche_event", _async_return(False))
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "get_arena_revanche_event_payload",
        _async_return(None),
    )
    monkeypatch.setattr(
        revanche.DuelLimitService,
        "resolve_revanche_access_type",
        _append_label_and_return(calls, "resolve_access", "FREE"),
    )
    monkeypatch.setattr(
        revanche,
        "create_revanche_friend_challenge",
        _async_return(SimpleNamespace(challenge_id=CHALLENGE_ID)),
    )
    monkeypatch.setattr(
        revanche.AnalyticsRepo,
        "create_arena_revanche_event_once",
        _append_kwargs_and_return([], True),
    )

    request = await _prepare_request()

    assert request.challenge is not None
    assert calls == ["sender_quota_lock", "event_lock", "resolve_access"]


async def _prepare_request():
    return await revanche.prepare_arena_revanche_request(
        AsyncSessionStub(),
        sender_user_id=11,
        source_attempt_id=SOURCE_ATTEMPT_ID,
        now_utc=NOW_UTC,
    )


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _append_kwargs(target: list[dict[str, object]]):
    async def _inner(*_args, **kwargs):
        target.append(kwargs)

    return _inner


def _append_kwargs_and_return(target: list[dict[str, object]], value: object):
    async def _inner(*_args, **kwargs):
        target.append(kwargs)
        return value

    return _inner


def _append_label(target: list[str], label: str):
    async def _inner(*_args, **_kwargs):
        target.append(label)

    return _inner


def _append_label_and_return(target: list[str], label: str, value: object):
    async def _inner(*_args, **_kwargs):
        target.append(label)
        return value

    return _inner


def _fail(message: str):
    async def _inner(*_args, **_kwargs):
        pytest.fail(message)

    return _inner
