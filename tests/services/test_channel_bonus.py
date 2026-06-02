from __future__ import annotations

from datetime import datetime, timedelta, timezone
from logging import WARNING
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import GetChatMember

from app.services import channel_bonus, channel_bonus_subscription
from app.services.channel_bonus import ChannelBonusService
from tests.bot.helpers import DummyBot
from tests.type_helpers import AsyncSessionStub


class _Session(AsyncSessionStub):
    async def flush(self, objects: object | None = None) -> None:
        del objects
        return None


class _FakeBot(DummyBot):
    def __init__(self, *, status: str = "member", error: Exception | None = None) -> None:
        super().__init__()
        self._status = status
        self._error = error

    async def get_chat_member(self, *, chat_id, user_id):
        del chat_id, user_id
        if self._error is not None:
            raise self._error
        return SimpleNamespace(status=self._status)


def _get_chat_member_method() -> GetChatMember:
    return GetChatMember(chat_id="@quiz_arena_test", user_id=503)


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
        return SimpleNamespace(free_energy=10, paid_energy=0)

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

    session = _Session()

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

    session = _Session()

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
async def test_claim_bonus_asks_user_to_retry_when_participant_id_is_invalid(
    monkeypatch,
    caplog,
) -> None:
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
    caplog.set_level(WARNING)

    session = _Session()

    result = await ChannelBonusService.claim_bonus_if_subscribed(
        session,
        user_id=303,
        telegram_user_id=503,
        bot=_FakeBot(
            error=TelegramBadRequest(
                method=_get_chat_member_method(),
                message="PARTICIPANT_ID_INVALID",
            )
        ),
        now_utc=datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc),
    )

    assert result.status == ChannelBonusService.STATUS_CHECK_RETRY
    assert result.reason == "participant_id_invalid"
    assert "channel_bonus_participant_id_invalid" in caplog.text


@pytest.mark.asyncio
async def test_claim_bonus_keeps_config_errors_separate_from_user_retry(
    monkeypatch,
    caplog,
) -> None:
    async def _fail_fill_to_free_cap(*args, **kwargs):
        raise AssertionError("bonus must not be granted when channel config is broken")

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
    caplog.set_level(WARNING)

    result = await ChannelBonusService.claim_bonus_if_subscribed(
        _Session(),
        user_id=303,
        telegram_user_id=503,
        bot=_FakeBot(
            error=TelegramBadRequest(
                method=_get_chat_member_method(),
                message="Bad Request: chat not found",
            )
        ),
        now_utc=datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc),
    )

    assert result.status == ChannelBonusService.STATUS_CHECK_ERROR
    assert result.reason == "bot_or_channel_config_broken"
    assert "channel_bonus_check_bad_request" in caplog.text


@pytest.mark.asyncio
async def test_claim_bonus_asks_user_to_retry_when_telegram_error_is_temporary(
    monkeypatch,
    caplog,
) -> None:
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
    caplog.set_level(WARNING)

    result = await ChannelBonusService.claim_bonus_if_subscribed(
        _Session(),
        user_id=303,
        telegram_user_id=503,
        bot=_FakeBot(
            error=TelegramNetworkError(
                method=_get_chat_member_method(),
                message="temporary network error",
            )
        ),
        now_utc=datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc),
    )

    assert result.status == ChannelBonusService.STATUS_CHECK_RETRY
    assert result.reason == "telegram_temporary_error"
    assert "channel_bonus_check_temporary_error" in caplog.text


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
        return SimpleNamespace(free_energy=10, paid_energy=0)

    monkeypatch.setattr(
        channel_bonus,
        "get_settings",
        lambda: SimpleNamespace(
            bonus_channel_id="@quiz_arena_test",
            bonus_check_bot_token="checker-token",
        ),
    )
    monkeypatch.setattr(channel_bonus_subscription, "Bot", _FakeCheckerBot)
    monkeypatch.setattr(channel_bonus.UsersRepo, "get_by_id_for_update", _fake_get_user_for_update)
    monkeypatch.setattr(channel_bonus.EnergyService, "fill_to_free_cap", _fake_fill_to_free_cap)

    session = _Session()

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
    monkeypatch.setattr(channel_bonus_subscription, "Bot", _InvalidCheckerBot)

    session = _Session()

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

    can_show = await ChannelBonusService.can_show_prompt(_Session(), user_id=404)

    assert can_show is False
