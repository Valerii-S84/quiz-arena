from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.db.repo.analytics_repo import AnalyticsRepo
from app.db.repo.arena_duels_repo import ArenaDuelsRepo
from app.game.arena_duels.constants import ARENA_REVANCHE_SENT_EVENT
from app.game.arena_duels.errors import ArenaDuelPaymentRequiredError
from app.game.duels import limits as duel_limits
from app.game.duels.limits import DUEL_ACCESS_FREE, DUEL_ACCESS_PAID_TICKET, DUEL_ACCESS_PREMIUM
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
BERLIN_DAY_START_UTC = datetime(2026, 4, 30, 22, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_arena_create_free_once_per_berlin_day_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    _patch_limit_dependencies(monkeypatch, arena_create_free=0, captured=captured)

    access_type = await duel_limits.DuelLimitService.resolve_arena_create_access_type(
        AsyncSessionStub(),
        user_id=11,
        now_utc=NOW_UTC,
    )

    assert access_type == DUEL_ACCESS_FREE
    assert captured["arena_create_since"] == BERLIN_DAY_START_UTC


@pytest.mark.asyncio
async def test_arena_create_second_free_attempt_requires_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_limit_dependencies(monkeypatch, arena_create_free=1)

    with pytest.raises(ArenaDuelPaymentRequiredError):
        await duel_limits.DuelLimitService.resolve_arena_create_access_type(
            AsyncSessionStub(),
            user_id=11,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_arena_accept_three_free_per_berlin_day_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    _patch_limit_dependencies(monkeypatch, arena_accept_free=2, captured=captured)

    access_type = await duel_limits.DuelLimitService.resolve_arena_accept_access_type(
        AsyncSessionStub(),
        user_id=11,
        now_utc=NOW_UTC,
    )

    assert access_type == DUEL_ACCESS_FREE
    assert captured["arena_accept_since"] == BERLIN_DAY_START_UTC


@pytest.mark.asyncio
async def test_arena_accept_fourth_free_attempt_requires_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_limit_dependencies(monkeypatch, arena_accept_free=3)

    with pytest.raises(ArenaDuelPaymentRequiredError):
        await duel_limits.DuelLimitService.resolve_arena_accept_access_type(
            AsyncSessionStub(),
            user_id=11,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_paid_ticket_allows_arena_after_free_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_limit_dependencies(monkeypatch, arena_create_free=1, tickets=1)

    access_type = await duel_limits.DuelLimitService.resolve_arena_create_access_type(
        AsyncSessionStub(),
        user_id=11,
        now_utc=NOW_UTC,
    )

    assert access_type == DUEL_ACCESS_PAID_TICKET


@pytest.mark.asyncio
async def test_premium_allows_arena_without_ticket_or_free_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_limit_dependencies(monkeypatch, premium=True, arena_create_free=99)

    access_type = await duel_limits.DuelLimitService.resolve_arena_create_access_type(
        AsyncSessionStub(),
        user_id=11,
        now_utc=NOW_UTC,
    )

    assert access_type == DUEL_ACCESS_PREMIUM


@pytest.mark.asyncio
async def test_revanche_free_quota_counts_free_access_sends_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    _patch_limit_dependencies(monkeypatch, revanche_free=0, captured=captured)

    access_type = await duel_limits.DuelLimitService.resolve_revanche_access_type(
        AsyncSessionStub(),
        user_id=11,
        now_utc=NOW_UTC,
    )

    assert access_type == DUEL_ACCESS_FREE
    assert captured["revanche_event_type"] == ARENA_REVANCHE_SENT_EVENT
    assert captured["revanche_since"] == BERLIN_DAY_START_UTC
    assert captured["revanche_payload_key"] == "access_type"
    assert captured["revanche_payload_value"] == DUEL_ACCESS_FREE


@pytest.mark.asyncio
async def test_revanche_free_limit_requires_payment_after_free_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_limit_dependencies(monkeypatch, revanche_free=1)

    with pytest.raises(ArenaDuelPaymentRequiredError):
        await duel_limits.DuelLimitService.resolve_revanche_access_type(
            AsyncSessionStub(),
            user_id=11,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_revanche_paid_ticket_allowed_after_free_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_limit_dependencies(monkeypatch, revanche_free=1, tickets=1)

    access_type = await duel_limits.DuelLimitService.resolve_revanche_access_type(
        AsyncSessionStub(),
        user_id=11,
        now_utc=NOW_UTC,
    )

    assert access_type == DUEL_ACCESS_PAID_TICKET


@pytest.mark.asyncio
async def test_revanche_paid_ticket_usage_counts_paid_revanche_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    _patch_limit_dependencies(
        monkeypatch,
        revanche_free=1,
        revanche_paid=1,
        tickets=1,
        captured=captured,
    )

    with pytest.raises(ArenaDuelPaymentRequiredError):
        await duel_limits.DuelLimitService.resolve_revanche_access_type(
            AsyncSessionStub(),
            user_id=11,
            now_utc=NOW_UTC,
        )

    assert captured["paid_revanche_event_type"] == ARENA_REVANCHE_SENT_EVENT
    assert captured["paid_revanche_payload_key"] == "access_type"
    assert captured["paid_revanche_payload_value"] == DUEL_ACCESS_PAID_TICKET


def _patch_limit_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    premium: bool = False,
    arena_create_free: int = 0,
    arena_accept_free: int = 0,
    revanche_free: int = 0,
    revanche_paid: int = 0,
    arena_paid: int = 0,
    friend_paid: int = 0,
    tickets: int = 0,
    captured: dict[str, object] | None = None,
) -> None:
    capture = captured if captured is not None else {}

    async def _get_user(*_args, **_kwargs):
        return SimpleNamespace(id=11)

    async def _has_premium(*_args, **_kwargs):
        return premium

    async def _count_creator_duels(*_args, **kwargs):
        capture["arena_create_since"] = kwargs["since"]
        return arena_create_free

    async def _count_challenger_attempts(*_args, **kwargs):
        capture["arena_accept_since"] = kwargs["since"]
        return arena_accept_free

    async def _count_revanche_events(*_args, **kwargs):
        capture["revanche_event_type"] = kwargs["event_type"]
        capture["revanche_since"] = kwargs["since_utc"]
        capture["revanche_payload_key"] = kwargs["payload_key"]
        capture["revanche_payload_value"] = kwargs["payload_value"]
        return revanche_free

    async def _count_paid_revanche_events(*_args, **kwargs):
        capture["paid_revanche_event_type"] = kwargs["event_type"]
        capture["paid_revanche_payload_key"] = kwargs["payload_key"]
        capture["paid_revanche_payload_value"] = kwargs["payload_value"]
        return revanche_paid

    async def _count_arena_paid(*_args, **_kwargs):
        return arena_paid

    async def _count_friend_paid(*_args, **_kwargs):
        return friend_paid

    async def _count_tickets(*_args, **_kwargs):
        return tickets

    monkeypatch.setattr(duel_limits.UsersRepo, "get_by_id_for_update", _get_user)
    monkeypatch.setattr(duel_limits.EntitlementsRepo, "has_active_premium", _has_premium)
    monkeypatch.setattr(
        ArenaDuelsRepo,
        "count_creator_duels_by_access_type",
        _count_creator_duels,
    )
    monkeypatch.setattr(
        ArenaDuelsRepo,
        "count_challenger_attempts_by_access_type",
        _count_challenger_attempts,
    )
    monkeypatch.setattr(ArenaDuelsRepo, "count_paid_ticket_usage", _count_arena_paid)
    monkeypatch.setattr(
        AnalyticsRepo,
        "count_user_events_since_by_payload_value",
        _count_revanche_events,
    )
    monkeypatch.setattr(
        duel_limits.FriendChallengesRepo,
        "count_by_creator_access_type_excluding_arena_revanche",
        _count_friend_paid,
    )
    monkeypatch.setattr(
        AnalyticsRepo,
        "count_user_events_by_payload_value",
        _count_paid_revanche_events,
    )
    monkeypatch.setattr(duel_limits.PurchasesRepo, "count_credited_product", _count_tickets)
