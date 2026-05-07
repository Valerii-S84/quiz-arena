from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from app.bot.handlers import gameplay_callbacks
from app.bot.handlers.gameplay_flows import arena_revanche_delivery, arena_revanche_flow

from .support import (
    OPPONENT_ATTEMPT_ID,
    SessionLocalStub,
    UserServiceWithTelegramStub,
    callback_data_list,
    make_callback,
    require_text,
)


@pytest.mark.asyncio
async def test_arena_revanche_confirm_shows_confirmation_without_push() -> None:
    async def load_context(*_args, **_kwargs):
        return SimpleNamespace(receiver_user_id=11)

    callback = make_callback(f"arena:revanche:{OPPONENT_ATTEMPT_ID}")
    await arena_revanche_flow.handle_arena_revanche_confirm(
        callback,
        arena_revanche_re=gameplay_callbacks.ARENA_REVANCHE_RE,
        parse_uuid_callback=lambda **_kwargs: OPPONENT_ATTEMPT_ID,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceWithTelegramStub,
        load_arena_revanche_context=load_context,
    )

    response = callback.message.answers[0]
    assert "Max erhält genau eine Nachricht." in require_text(response.text)
    assert callback_data_list(response.kwargs["reply_markup"]) == [
        f"arena:revanche_send:{OPPONENT_ATTEMPT_ID}",
        "arena:list",
    ]
    assert callback.bot.sent_messages == []


@pytest.mark.asyncio
async def test_arena_revanche_send_creates_one_push_and_records_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    recorded: list[dict[str, object]] = []

    async def prepare(*_args, **_kwargs):
        return SimpleNamespace(
            already_sent=False,
            context=SimpleNamespace(receiver_user_id=11),
            challenge=SimpleNamespace(challenge_id=challenge_id),
        )

    async def record(*_args, **kwargs):
        recorded.append(kwargs)
        return True

    async def cleanup(*_args, **_kwargs):
        pytest.fail("successful Revanche push must not cleanup")

    async def lock(*_args, **_kwargs):
        return None

    async def is_sent(*_args, **_kwargs):
        return False

    monkeypatch.setattr(arena_revanche_delivery, "lock_arena_revanche_delivery", lock)
    monkeypatch.setattr(arena_revanche_delivery, "is_arena_revanche_sent", is_sent)

    callback = make_callback(f"arena:revanche_send:{OPPONENT_ATTEMPT_ID}")
    await arena_revanche_flow.handle_arena_revanche_send(
        callback,
        arena_revanche_send_re=gameplay_callbacks.ARENA_REVANCHE_SEND_RE,
        parse_uuid_callback=lambda **_kwargs: OPPONENT_ATTEMPT_ID,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceWithTelegramStub,
        prepare_arena_revanche_request=prepare,
        record_arena_revanche_sent=record,
        cleanup_arena_revanche_request=cleanup,
    )

    assert len(callback.bot.sent_messages) == 1
    sent = callback.bot.sent_messages[0]
    assert sent["chat_id"] == 110_000_011
    assert "@anna fordert dich zur Revanche heraus." in str(sent["text"])
    assert callback_data_list(sent["reply_markup"]) == [f"friend:next:{challenge_id}", "home:open"]
    recorded_request = cast(Any, recorded[0]["request"])
    assert recorded_request.challenge.challenge_id == challenge_id
    assert "Revanche gesendet." in require_text(callback.message.answers[0].text)
    assert callback_data_list(callback.message.answers[0].kwargs["reply_markup"]) == ["arena:list"]


@pytest.mark.asyncio
async def test_arena_revanche_send_dedupes_existing_request_without_push() -> None:
    async def prepare(*_args, **_kwargs):
        return SimpleNamespace(
            already_sent=True,
            context=SimpleNamespace(receiver_user_id=11),
            challenge=None,
        )

    async def unexpected_record(*_args, **_kwargs):
        pytest.fail("duplicate Revanche tap must not record or push again")

    async def unexpected_cleanup(*_args, **_kwargs):
        pytest.fail("duplicate Revanche tap must not cleanup")

    callback = make_callback(f"arena:revanche_send:{OPPONENT_ATTEMPT_ID}")
    await arena_revanche_flow.handle_arena_revanche_send(
        callback,
        arena_revanche_send_re=gameplay_callbacks.ARENA_REVANCHE_SEND_RE,
        parse_uuid_callback=lambda **_kwargs: OPPONENT_ATTEMPT_ID,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceWithTelegramStub,
        prepare_arena_revanche_request=prepare,
        record_arena_revanche_sent=unexpected_record,
        cleanup_arena_revanche_request=unexpected_cleanup,
    )

    assert callback.bot.sent_messages == []
    assert "Revanche gesendet." in require_text(callback.message.answers[0].text)
