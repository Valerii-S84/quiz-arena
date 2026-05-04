from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.bot.handlers import gameplay_callbacks, gameplay_duels
from app.bot.texts.de import TEXTS_DE
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


def _callback_payloads(reply_markup) -> list[str]:
    return [
        button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


class _RecordingRouter:
    def __init__(self) -> None:
        self.handlers: list[Callable[..., object]] = []

    def callback_query(
        self, _filter: object
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        def _decorator(handler: Callable[..., object]) -> Callable[..., object]:
            self.handlers.append(handler)
            return handler

        return _decorator


@pytest.mark.asyncio
async def test_duels_menu_handler_shows_only_clean_mode_choices() -> None:
    callback = DummyCallback(
        data="duels:menu",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_duels.handle_duels_menu(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.duels.menu"]
    assert _callback_payloads(response.kwargs["reply_markup"]) == [
        "duels:arena",
        "duels:friend",
        "home:open",
    ]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_duels_menu_handler_blocks_canonical_rollout_when_flag_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gameplay_duels.duel_rollout, "is_canonical_duels_enabled", lambda: False)
    callback = DummyCallback(
        data="duels:menu",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_duels.handle_duels_menu(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.duels.disabled"]
    assert _callback_payloads(response.kwargs["reply_markup"]) == [
        "daily_challenge",
        "duels:menu",
        "play",
        "mode:ARTIKEL_SPRINT",
        "shop:open",
    ]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_friend_duel_handler_uses_direct_seven_question_create_callback() -> None:
    callback = DummyCallback(
        data="duels:friend",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_duels.handle_friend_duel_open(callback)

    response = callback.message.answers[0]
    callbacks = _callback_payloads(response.kwargs["reply_markup"])
    assert response.text == TEXTS_DE["msg.duels.friend"]
    assert callbacks == ["friend:challenge:format:direct:7", "duels:menu"]
    assert "friend:challenge:create" not in callbacks
    assert "friend:challenge:type:direct" not in callbacks
    assert "friend:challenge:format:direct:5" not in callbacks
    assert "friend:challenge:format:direct:12" not in callbacks
    assert "friend:tournament:create" not in callbacks
    assert "create_tournament_start" not in callbacks
    assert "friend:tournament:format:5" not in callbacks
    assert "friend:tournament:format:12" not in callbacks


@pytest.mark.asyncio
async def test_friend_duel_handler_emits_canonical_open_event_without_replacing_mode_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[dict[str, object]] = []

    async def _fake_home_snapshot(_session, *, telegram_user):
        assert telegram_user.id == 17
        return SimpleNamespace(user_id=101)

    async def _fake_emit(_session, **kwargs) -> None:
        emitted.append(kwargs)

    monkeypatch.setattr(gameplay_duels, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(
        gameplay_duels.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_home_snapshot,
    )
    monkeypatch.setattr(gameplay_duels, "emit_arena_analytics_event", _fake_emit)

    callback = DummyCallback(
        data="duels:friend",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_duels.handle_friend_duel_open(callback, emit_event=True)

    assert [event["event_type"] for event in emitted] == [
        gameplay_duels.ARENA_EVENT_DUEL_MODE_SELECTED,
        gameplay_duels.ARENA_EVENT_FRIEND_DUEL_OPENED,
    ]
    assert emitted[0]["payload"] == {"user_id": 101, "action": "friend"}
    assert emitted[1]["payload"] == {"user_id": 101}


@pytest.mark.asyncio
async def test_arena_create_handler_has_start_and_arena_back_only() -> None:
    callback = DummyCallback(
        data="arena:create",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_duels.handle_arena_create(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.duels.arena.create"]
    assert _callback_payloads(response.kwargs["reply_markup"]) == [
        "arena:start_create",
        "arena:list",
    ]


@pytest.mark.asyncio
async def test_arena_publish_friend_handler_delegates_to_flow(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_publish_flow(callback, **kwargs):
        captured["callback"] = callback
        captured.update(kwargs)

    monkeypatch.setattr(
        gameplay_duels.arena_duel_flow,
        "handle_arena_publish_friend",
        _fake_publish_flow,
    )
    callback = DummyCallback(
        data="arena:publish_friend:00000000-0000-0000-0000-000000000001",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_duels.handle_arena_publish_friend(callback)

    assert captured["callback"] is callback
    assert captured["arena_publish_friend_re"] is gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE
    assert captured["parse_uuid_callback"] is gameplay_callbacks.parse_uuid_callback
    assert captured["publish_friend_challenge_to_arena"] is (
        gameplay_duels.publish_friend_challenge_to_arena
    )


@pytest.mark.asyncio
async def test_arena_publish_friend_handler_blocks_rollout_when_flag_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _fake_publish_flow(callback, **kwargs):
        del callback, kwargs
        nonlocal called
        called = True

    monkeypatch.setattr(gameplay_duels.duel_rollout, "is_canonical_duels_enabled", lambda: False)
    monkeypatch.setattr(
        gameplay_duels.arena_duel_flow,
        "handle_arena_publish_friend",
        _fake_publish_flow,
    )
    callback = DummyCallback(
        data="arena:publish_friend:00000000-0000-0000-0000-000000000001",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_duels.handle_arena_publish_friend(callback)

    assert called is False
    assert callback.message.answers[0].text == TEXTS_DE["msg.duels.disabled"]


@pytest.mark.asyncio
async def test_arena_revanche_handlers_delegate_to_flow(monkeypatch) -> None:
    captured: list[dict[str, object]] = []

    async def _fake_confirm_flow(callback, **kwargs):
        captured.append({"callback": callback, **kwargs})

    async def _fake_send_flow(callback, **kwargs):
        captured.append({"callback": callback, **kwargs})

    monkeypatch.setattr(
        gameplay_duels.arena_revanche_flow,
        "handle_arena_revanche_confirm",
        _fake_confirm_flow,
    )
    monkeypatch.setattr(
        gameplay_duels.arena_revanche_flow,
        "handle_arena_revanche_send",
        _fake_send_flow,
    )

    confirm_callback = DummyCallback(
        data="arena:revanche:00000000-0000-0000-0000-000000000001",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    send_callback = DummyCallback(
        data="arena:revanche_send:00000000-0000-0000-0000-000000000001",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_duels.handle_arena_revanche_confirm(confirm_callback)
    await gameplay_duels.handle_arena_revanche_send(send_callback)

    assert captured[0]["callback"] is confirm_callback
    assert captured[0]["arena_revanche_re"] is gameplay_callbacks.ARENA_REVANCHE_RE
    assert captured[0]["load_arena_revanche_context"] is gameplay_duels.load_arena_revanche_context
    assert captured[1]["callback"] is send_callback
    assert captured[1]["arena_revanche_send_re"] is gameplay_callbacks.ARENA_REVANCHE_SEND_RE
    assert captured[1]["prepare_arena_revanche_request"] is (
        gameplay_duels.prepare_arena_revanche_request
    )
    assert captured[1]["record_arena_revanche_sent"] is gameplay_duels.record_arena_revanche_sent
    assert captured[1]["cleanup_arena_revanche_request"] is (
        gameplay_duels.cleanup_arena_revanche_request
    )


def test_duels_register_includes_arena_callbacks() -> None:
    router = _RecordingRouter()

    gameplay_duels.register(cast(Any, router))

    assert gameplay_duels.handle_arena_publish_friend in router.handlers
    assert gameplay_duels.handle_arena_revanche_confirm in router.handlers
    assert gameplay_duels.handle_arena_revanche_send in router.handlers
