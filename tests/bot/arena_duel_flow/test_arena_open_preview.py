from types import SimpleNamespace

import pytest

from app.bot.handlers.gameplay_flows import arena_duel_flow
from app.game.arena_duels.errors import (
    ArenaDuelAlreadyAttemptedError,
    ArenaDuelExpiredError,
    ArenaDuelOwnAttemptError,
)

from .support import (
    DUEL_ID,
    SessionLocalStub,
    UserServiceStub,
    active_duel,
    callback_data_list,
    make_callback,
    require_text,
)


@pytest.mark.asyncio
async def test_arena_open_lists_active_duels_with_accept_buttons() -> None:
    async def list_active(*_args, **_kwargs):
        return (active_duel(),)

    callback = make_callback("duels:arena")
    await arena_duel_flow.handle_arena_open(
        callback,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
        list_active_arena_duels=list_active,
    )

    response = callback.message.answers[0]
    text = require_text(response.text)
    assert "🏟 Offene Arena" in text
    assert "Max" in text
    assert "6/7 · 00:48" in text
    assert callback_data_list(response.kwargs["reply_markup"]) == [
        f"arena:accept:{DUEL_ID}",
        "arena:create",
        "duels:menu",
    ]


@pytest.mark.asyncio
async def test_arena_open_uses_empty_state_when_no_active_duels() -> None:
    async def list_active(*_args, **_kwargs):
        return ()

    callback = make_callback("duels:arena")
    await arena_duel_flow.handle_arena_open(
        callback,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
        list_active_arena_duels=list_active,
    )

    response = callback.message.answers[0]
    assert "Noch gibt es keine aktiven Arena-Duelle." in require_text(response.text)
    assert callback_data_list(response.kwargs["reply_markup"]) == ["arena:create", "duels:menu"]


@pytest.mark.asyncio
async def test_arena_accept_preview_shows_start_screen() -> None:
    async def preview(*_args, **_kwargs):
        return active_duel()

    callback = make_callback(f"arena:accept:{DUEL_ID}")
    await arena_duel_flow.handle_arena_accept_preview(
        callback,
        arena_accept_re=SimpleNamespace(match=lambda value: value.startswith("arena:accept:")),
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
        get_arena_duel_accept_preview=preview,
    )

    response = callback.message.answers[0]
    text = require_text(response.text)
    assert "Schlage das Ergebnis von Max." in text
    assert "6/7 · 00:48" in text
    assert callback_data_list(response.kwargs["reply_markup"]) == [
        f"arena:start_attempt:{DUEL_ID}",
        "arena:list",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_text", "expected_callbacks"),
    [
        (ArenaDuelOwnAttemptError, "Das ist dein eigenes Arena-Duell.", ["arena:list"]),
        (
            ArenaDuelAlreadyAttemptedError,
            "Du hast dieses Arena-Duell bereits gespielt.",
            ["arena:list"],
        ),
        (ArenaDuelExpiredError, "Dieses Duell ist abgelaufen.", ["arena:create", "arena:list"]),
    ],
)
async def test_arena_accept_preview_maps_guards_to_clean_messages(
    error,
    expected_text,
    expected_callbacks,
) -> None:
    async def preview(*_args, **_kwargs):
        raise error

    callback = make_callback(f"arena:accept:{DUEL_ID}")
    await arena_duel_flow.handle_arena_accept_preview(
        callback,
        arena_accept_re=SimpleNamespace(match=lambda value: value.startswith("arena:accept:")),
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
        get_arena_duel_accept_preview=preview,
    )

    assert expected_text in require_text(callback.message.answers[0].text)
    assert (
        callback_data_list(callback.message.answers[0].kwargs["reply_markup"]) == expected_callbacks
    )
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
