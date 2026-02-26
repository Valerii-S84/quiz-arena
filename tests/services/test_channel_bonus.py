from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import channel_bonus
from app.services.channel_bonus import ChannelBonusService


class _FakeBot:
    def __init__(self, *, status: str = "member", error: Exception | None = None) -> None:
        self._status = status
        self._error = error

    async def get_chat_member(self, *, chat_id, user_id):
        del chat_id, user_id
        if self._error is not None:
            raise self._error
        return SimpleNamespace(status=self._status)


@pytest.mark.asyncio
async def test_claim_bonus_grants_energy_only_once_when_subscribed(monkeypatch) -> None:
    now_utc = datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc)
    user = SimpleNamespace(channel_bonus_claimed_at=None)
    fill_calls = 0

    async def _fake_get_user_for_update(session, user_id: int):
        del session, user_id
        return user

    async def _fake_fill_to_free_cap(session, *, user_id: int, now_utc):
        nonlocal fill_calls
        del session, user_id, now_utc
        fill_calls += 1
        return SimpleNamespace(free_energy=20, paid_energy=0)

    monkeypatch.setattr(
        channel_bonus,
        "get_settings",
        lambda: SimpleNamespace(bonus_channel_id="@quiz_arena_test"),
    )
    monkeypatch.setattr(
        channel_bonus.UsersRepo,
        "get_by_id_for_update",
        _fake_get_user_for_update,
    )
    monkeypatch.setattr(
        channel_bonus.EnergyService,
        "fill_to_free_cap",
        _fake_fill_to_free_cap,
    )

    session = SimpleNamespace(flush=lambda: None)

    async def _flush() -> None:
        return None

    session.flush = _flush

    first = await ChannelBonusService.claim_bonus_if_subscribed(
        session,
        user_id=101,
        telegram_user_id=301,
        bot=_FakeBot(status="member"),
        now_utc=now_utc,
    )
    second = await ChannelBonusService.claim_bonus_if_subscribed(
        session,
        user_id=101,
        telegram_user_id=301,
        bot=_FakeBot(status="member"),
        now_utc=now_utc + timedelta(minutes=1),
    )

    assert first.status == ChannelBonusService.STATUS_CLAIMED
    assert second.status == ChannelBonusService.STATUS_ALREADY_CLAIMED
    assert fill_calls == 1


@pytest.mark.asyncio
async def test_claim_bonus_does_not_grant_when_not_subscribed(monkeypatch) -> None:
    user = SimpleNamespace(channel_bonus_claimed_at=None)

    async def _fake_get_user_for_update(session, user_id: int):
        del session, user_id
        return user

    async def _fail_fill_to_free_cap(*args, **kwargs):
        raise AssertionError("bonus must not be granted for non-subscribed users")

    monkeypatch.setattr(
        channel_bonus,
        "get_settings",
        lambda: SimpleNamespace(bonus_channel_id="@quiz_arena_test"),
    )
    monkeypatch.setattr(
        channel_bonus.UsersRepo,
        "get_by_id_for_update",
        _fake_get_user_for_update,
    )
    monkeypatch.setattr(
        channel_bonus.EnergyService,
        "fill_to_free_cap",
        _fail_fill_to_free_cap,
    )

    session = SimpleNamespace(flush=lambda: None)

    async def _flush() -> None:
        return None

    session.flush = _flush

    result = await ChannelBonusService.claim_bonus_if_subscribed(
        session,
        user_id=202,
        telegram_user_id=402,
        bot=_FakeBot(status="left"),
        now_utc=datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc),
    )

    assert result.status == ChannelBonusService.STATUS_NOT_SUBSCRIBED
    assert user.channel_bonus_claimed_at is None


@pytest.mark.asyncio
async def test_claim_bonus_does_not_grant_when_check_fails(monkeypatch) -> None:
    async def _fail_fill_to_free_cap(*args, **kwargs):
        raise AssertionError("bonus must not be granted when channel check fails")

    monkeypatch.setattr(
        channel_bonus,
        "get_settings",
        lambda: SimpleNamespace(bonus_channel_id="@quiz_arena_test"),
    )
    monkeypatch.setattr(
        channel_bonus.EnergyService,
        "fill_to_free_cap",
        _fail_fill_to_free_cap,
    )

    session = SimpleNamespace(flush=lambda: None)

    async def _flush() -> None:
        return None

    session.flush = _flush

    result = await ChannelBonusService.claim_bonus_if_subscribed(
        session,
        user_id=303,
        telegram_user_id=503,
        bot=_FakeBot(error=TimeoutError("network timeout")),
        now_utc=datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc),
    )

    assert result.status == ChannelBonusService.STATUS_CHECK_ERROR


@pytest.mark.asyncio
async def test_claim_bonus_uses_dedicated_checker_bot_token(monkeypatch) -> None:
    now_utc = datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc)
    user = SimpleNamespace(channel_bonus_claimed_at=None)
    created_tokens: list[str] = []

    class _FakeCheckerBot:
        def __init__(self, *, token: str) -> None:
            created_tokens.append(token)

            async def _close() -> None:
                return None

            self.session = SimpleNamespace(close=_close)

        async def get_chat_member(self, *, chat_id, user_id):
            del chat_id, user_id
            return SimpleNamespace(status="member")

    async def _fake_get_user_for_update(session, user_id: int):
        del session, user_id
        return user

    async def _fake_fill_to_free_cap(session, *, user_id: int, now_utc):
        del session, user_id, now_utc
        return SimpleNamespace(free_energy=20, paid_energy=0)

    monkeypatch.setattr(
        channel_bonus,
        "get_settings",
        lambda: SimpleNamespace(
            bonus_channel_id="@quiz_arena_test",
            bonus_check_bot_token="checker-token",
        ),
    )
    monkeypatch.setattr(channel_bonus, "Bot", _FakeCheckerBot)
    monkeypatch.setattr(channel_bonus.UsersRepo, "get_by_id_for_update", _fake_get_user_for_update)
    monkeypatch.setattr(channel_bonus.EnergyService, "fill_to_free_cap", _fake_fill_to_free_cap)

    session = SimpleNamespace(flush=lambda: None)

    async def _flush() -> None:
        return None

    session.flush = _flush

    result = await ChannelBonusService.claim_bonus_if_subscribed(
        session,
        user_id=505,
        telegram_user_id=605,
        bot=_FakeBot(status="left"),
        now_utc=now_utc,
    )

    assert result.status == ChannelBonusService.STATUS_CLAIMED
    assert created_tokens == ["checker-token"]


@pytest.mark.asyncio
async def test_claim_bonus_returns_error_when_checker_token_invalid(monkeypatch) -> None:
    class _InvalidCheckerBot:
        def __init__(self, *, token: str) -> None:
            del token
            raise ValueError("invalid token")

    monkeypatch.setattr(
        channel_bonus,
        "get_settings",
        lambda: SimpleNamespace(
            bonus_channel_id="@quiz_arena_test",
            bonus_check_bot_token="invalid",
        ),
    )
    monkeypatch.setattr(channel_bonus, "Bot", _InvalidCheckerBot)

    session = SimpleNamespace(flush=lambda: None)

    async def _flush() -> None:
        return None

    session.flush = _flush

    result = await ChannelBonusService.claim_bonus_if_subscribed(
        session,
        user_id=707,
        telegram_user_id=807,
        bot=_FakeBot(status="member"),
        now_utc=datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc),
    )

    assert result.status == ChannelBonusService.STATUS_CHECK_ERROR


@pytest.mark.asyncio
async def test_can_show_prompt_returns_false_when_bonus_already_claimed(monkeypatch) -> None:
    async def _fake_get_user(session, user_id: int):
        del session, user_id
        return SimpleNamespace(
            channel_bonus_claimed_at=datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc)
        )

    monkeypatch.setattr(channel_bonus.UsersRepo, "get_by_id", _fake_get_user)

    can_show = await ChannelBonusService.can_show_prompt(SimpleNamespace(), user_id=404)

    assert can_show is False
