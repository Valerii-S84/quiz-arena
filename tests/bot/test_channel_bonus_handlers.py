from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.handlers import channel_bonus
from app.bot.texts.de import TEXTS_DE
from app.services.channel_bonus import ChannelBonusService
from tests.bot.helpers import DummyCallback, DummyMessage


class _SessionBegin:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _SessionLocal:
    def __init__(self, session: object) -> None:
        self._session = session

    def begin(self) -> _SessionBegin:
        return _SessionBegin(self._session)


@pytest.mark.asyncio
async def test_show_channel_bonus_offer_returns_false_when_prompt_hidden(monkeypatch) -> None:
    session = object()
    events: list[str] = []
    message = DummyMessage()

    async def _fake_can_show(_session, *, user_id: int) -> bool:
        assert _session is session
        assert user_id == 17
        return False

    async def _fake_emit(*args, **kwargs) -> None:
        del args
        events.append(str(kwargs["event_type"]))

    monkeypatch.setattr(ChannelBonusService, "can_show_prompt", _fake_can_show)
    monkeypatch.setattr(channel_bonus, "emit_analytics_event", _fake_emit)

    shown = await channel_bonus._show_channel_bonus_offer(
        session=session,
        message=message,
        user_id=17,
        now_utc=object(),  # type: ignore[arg-type]
        source="shop",
    )

    assert shown is False
    assert message.answers == []
    assert events == []


@pytest.mark.asyncio
async def test_show_channel_bonus_offer_emits_event_and_sends_keyboard(monkeypatch) -> None:
    session = object()
    events: list[str] = []
    message = DummyMessage()

    async def _fake_can_show(_session, *, user_id: int) -> bool:
        assert _session is session
        assert user_id == 17
        return True

    async def _fake_emit(*args, **kwargs) -> None:
        del args
        events.append(str(kwargs["event_type"]))

    monkeypatch.setattr(ChannelBonusService, "can_show_prompt", _fake_can_show)
    monkeypatch.setattr(
        ChannelBonusService, "resolve_channel_url", lambda: "https://t.me/quizarena"
    )
    monkeypatch.setattr(channel_bonus, "emit_analytics_event", _fake_emit)

    shown = await channel_bonus._show_channel_bonus_offer(
        session=session,
        message=message,
        user_id=17,
        now_utc=object(),  # type: ignore[arg-type]
        source="shop",
    )

    answer = message.answers[0]
    assert shown is True
    assert events == ["channel_bonus_shown"]
    assert answer.text == channel_bonus._channel_bonus_offer_text()
    assert answer.kwargs["reply_markup"].inline_keyboard[0][0].url == "https://t.me/quizarena"


@pytest.mark.asyncio
async def test_handle_channel_bonus_open_rejects_invalid_callback_context() -> None:
    callback = DummyCallback(data="channel_bonus:open", from_user=None, message=DummyMessage())

    await channel_bonus.handle_channel_bonus_open(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_channel_bonus_open_shows_already_claimed_message_when_offer_not_shown(
    monkeypatch,
) -> None:
    session = object()
    captured: dict[str, object] = {}

    async def _fake_snapshot(_session, *, telegram_user):
        assert _session is session
        assert telegram_user.id == 77
        return SimpleNamespace(user_id=55)

    async def _fake_show_offer(**kwargs) -> bool:
        captured.update(kwargs)
        return False

    monkeypatch.setattr(channel_bonus, "Message", DummyMessage)
    monkeypatch.setattr(channel_bonus, "SessionLocal", _SessionLocal(session))
    monkeypatch.setattr(
        channel_bonus.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_snapshot,
    )
    monkeypatch.setattr(channel_bonus, "_show_channel_bonus_offer", _fake_show_offer)

    callback = DummyCallback(
        data="channel_bonus:open",
        from_user=SimpleNamespace(id=77),
        message=DummyMessage(),
    )
    await channel_bonus.handle_channel_bonus_open(callback)

    assert captured["session"] is session
    assert captured["message"] is callback.message
    assert captured["user_id"] == 55
    assert captured["source"] == "shop"
    assert callback.message.answers[0].text == TEXTS_DE["msg.channel.bonus.already_claimed"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_channel_bonus_open_answers_without_extra_message_when_offer_is_shown(
    monkeypatch,
) -> None:
    async def _fake_snapshot(_session, *, telegram_user):
        del _session
        assert telegram_user.id == 77
        return SimpleNamespace(user_id=55)

    async def _fake_show_offer(**kwargs) -> bool:
        del kwargs
        return True

    monkeypatch.setattr(channel_bonus, "Message", DummyMessage)
    monkeypatch.setattr(channel_bonus, "SessionLocal", _SessionLocal(object()))
    monkeypatch.setattr(
        channel_bonus.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_snapshot,
    )
    monkeypatch.setattr(channel_bonus, "_show_channel_bonus_offer", _fake_show_offer)

    callback = DummyCallback(
        data="channel_bonus:open",
        from_user=SimpleNamespace(id=77),
        message=DummyMessage(),
    )
    await channel_bonus.handle_channel_bonus_open(callback)

    assert callback.message.answers == []
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_channel_bonus_check_rejects_invalid_callback_context() -> None:
    callback = DummyCallback(data="channel_bonus:check", from_user=None, message=DummyMessage())

    await channel_bonus.handle_channel_bonus_check(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_channel_bonus_check_rejects_missing_bot(monkeypatch) -> None:
    monkeypatch.setattr(channel_bonus, "Message", DummyMessage)

    callback = DummyCallback(
        data="channel_bonus:check",
        from_user=SimpleNamespace(id=11),
        message=DummyMessage(),
    )
    callback.bot = None

    await channel_bonus.handle_channel_bonus_check(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_events", "expected_text"),
    [
        (
            ChannelBonusService.STATUS_CLAIMED,
            ["channel_bonus_check_started", "channel_bonus_claimed"],
            TEXTS_DE["msg.channel.bonus.success"],
        ),
        (
            ChannelBonusService.STATUS_NOT_SUBSCRIBED,
            [
                "channel_bonus_check_started",
                "channel_bonus_check_failed_not_subscribed",
            ],
            TEXTS_DE["msg.channel.bonus.not_subscribed"],
        ),
        (
            ChannelBonusService.STATUS_CHECK_ERROR,
            ["channel_bonus_check_started", "channel_bonus_check_failed_error"],
            TEXTS_DE["msg.channel.bonus.check.error"],
        ),
    ],
)
async def test_handle_channel_bonus_check_emits_expected_events_for_result_status(
    monkeypatch,
    status: str,
    expected_events: list[str],
    expected_text: str,
) -> None:
    session = object()
    events: list[str] = []

    async def _fake_snapshot(_session, *, telegram_user):
        assert _session is session
        assert telegram_user.id == 11
        return SimpleNamespace(user_id=42)

    async def _fake_emit(*args, **kwargs) -> None:
        del args
        events.append(str(kwargs["event_type"]))

    async def _fake_claim(_session, *, user_id: int, telegram_user_id: int, bot, now_utc):
        assert _session is session
        assert user_id == 42
        assert telegram_user_id == 11
        assert bot is callback.bot
        assert now_utc is not None
        return SimpleNamespace(status=status)

    monkeypatch.setattr(channel_bonus, "Message", DummyMessage)
    monkeypatch.setattr(channel_bonus, "SessionLocal", _SessionLocal(session))
    monkeypatch.setattr(
        channel_bonus.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_snapshot,
    )
    monkeypatch.setattr(channel_bonus, "emit_analytics_event", _fake_emit)
    monkeypatch.setattr(ChannelBonusService, "claim_bonus_if_subscribed", _fake_claim)

    callback = DummyCallback(
        data="channel_bonus:check",
        from_user=SimpleNamespace(id=11),
        message=DummyMessage(),
    )
    await channel_bonus.handle_channel_bonus_check(callback)

    assert events == expected_events
    assert callback.message.answers[0].text == expected_text
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_channel_bonus_check_already_claimed_branch_stays_silent(monkeypatch) -> None:
    events: list[str] = []

    async def _fake_snapshot(_session, *, telegram_user):
        del _session
        assert telegram_user.id == 11
        return SimpleNamespace(user_id=42)

    async def _fake_emit(*args, **kwargs) -> None:
        del args
        events.append(str(kwargs["event_type"]))

    async def _fake_claim(_session, *, user_id: int, telegram_user_id: int, bot, now_utc):
        del _session, bot, now_utc
        assert user_id == 42
        assert telegram_user_id == 11
        return SimpleNamespace(status=ChannelBonusService.STATUS_ALREADY_CLAIMED)

    monkeypatch.setattr(channel_bonus, "Message", DummyMessage)
    monkeypatch.setattr(channel_bonus, "SessionLocal", _SessionLocal(object()))
    monkeypatch.setattr(
        channel_bonus.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_snapshot,
    )
    monkeypatch.setattr(channel_bonus, "emit_analytics_event", _fake_emit)
    monkeypatch.setattr(ChannelBonusService, "claim_bonus_if_subscribed", _fake_claim)

    callback = DummyCallback(
        data="channel_bonus:check",
        from_user=SimpleNamespace(id=11),
        message=DummyMessage(),
    )
    await channel_bonus.handle_channel_bonus_check(callback)

    assert events == ["channel_bonus_check_started"]
    assert callback.message.answers == []
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
