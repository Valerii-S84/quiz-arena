from types import SimpleNamespace

import pytest

from app.bot.handlers.gameplay_flows import arena_duel_flow
from app.bot.handlers.gameplay_flows.arena_duel_flow_support import (
    DuelPaywallContext,
    resolve_duel_paywall_text,
)
from app.game.arena_duels.errors import ArenaDuelPaymentRequiredError
from app.game.arena_duels.types import ArenaBaselineStartResult
from app.game.sessions.errors import FriendChallengeAccessError

from .support import (
    ATTEMPT_ID,
    DUEL_ID,
    SessionLocalStub,
    UserServiceStub,
    callback_data_list,
    duel_snapshot,
    make_callback,
    require_text,
    start_result,
)

PAYWALL_CONTEXT_CASES: list[tuple[DuelPaywallContext, str]] = [
    ("close_loss", "Willst du sofort eine Revanche?"),
    ("revanche_limit", "Deine freie Revanche ist heute verbraucht."),
    ("arena_accept_limit", "Dein heutiges Arena-Duell-Limit ist erreicht."),
    ("friend_limit", "Deine freien Freundesduelle sind heute verbraucht."),
    ("beaten_result", "Willst du deinen Platz zurückholen?"),
]


@pytest.mark.asyncio
async def test_arena_start_create_starts_baseline_question() -> None:
    async def resolve_create_access(*_args, **_kwargs):
        return "FREE"

    async def create_baseline(*_args, **_kwargs):
        return ArenaBaselineStartResult(
            duel=duel_snapshot(),
            baseline_attempt_id=ATTEMPT_ID,
            start_result=start_result(),
        )

    callback = make_callback("arena:start_create")
    await arena_duel_flow.handle_arena_start_create(
        callback,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
        resolve_arena_create_access_type=resolve_create_access,
        create_arena_duel_baseline=create_baseline,
        build_question_text=lambda **_kwargs: "arena question",
    )

    response = callback.message.answers[0]
    assert response.text == "arena question"
    assert callback_data_list(response.kwargs["reply_markup"]) == [
        "answer:cccccccc-cccc-cccc-cccc-cccccccccccc:0",
        "answer:cccccccc-cccc-cccc-cccc-cccccccccccc:1",
        "answer:cccccccc-cccc-cccc-cccc-cccccccccccc:2",
        "answer:cccccccc-cccc-cccc-cccc-cccccccccccc:3",
        "game:stop:cccccccc-cccc-cccc-cccc-cccccccccccc",
    ]


@pytest.mark.asyncio
async def test_arena_start_create_limit_hit_shows_duel_paywall_without_start() -> None:
    async def resolve_create_access(*_args, **_kwargs):
        raise ArenaDuelPaymentRequiredError

    async def unexpected_create_baseline(*_args, **_kwargs):
        pytest.fail("direct arena:start_create must not bypass the duel limit")

    callback = make_callback("arena:start_create")
    await arena_duel_flow.handle_arena_start_create(
        callback,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
        resolve_arena_create_access_type=resolve_create_access,
        create_arena_duel_baseline=unexpected_create_baseline,
        build_question_text=lambda **_kwargs: "arena question",
    )

    response = callback.message.answers[0]
    assert "Dein heutiges Arena-Duell-Limit ist erreicht." in require_text(response.text)
    assert callback_data_list(response.kwargs["reply_markup"]) == [
        "buy:FRIEND_CHALLENGE_5:duel",
        "buy:PREMIUM_WEEK:duel",
        "arena:list",
    ]


@pytest.mark.asyncio
async def test_arena_start_attempt_maps_session_access_error_to_guard() -> None:
    async def resolve_accept_access(*_args, **_kwargs):
        return "FREE"

    async def accept(*_args, **_kwargs):
        raise FriendChallengeAccessError

    callback = make_callback(f"arena:start_attempt:{DUEL_ID}")
    await arena_duel_flow.handle_arena_start_attempt(
        callback,
        arena_start_attempt_re=SimpleNamespace(
            match=lambda value: value.startswith("arena:start_attempt:")
        ),
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
        resolve_arena_accept_access_type=resolve_accept_access,
        accept_arena_duel=accept,
        build_question_text=lambda **_kwargs: "arena question",
    )

    response = callback.message.answers[0]
    assert "Dieses Duell ist abgelaufen." in require_text(response.text)
    assert callback_data_list(response.kwargs["reply_markup"]) == ["arena:create", "arena:list"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_arena_start_attempt_limit_hit_shows_duel_paywall_without_accept() -> None:
    async def resolve_accept_access(*_args, **_kwargs):
        raise ArenaDuelPaymentRequiredError

    async def unexpected_accept(*_args, **_kwargs):
        pytest.fail("direct arena:start_attempt must not bypass the duel limit")

    callback = make_callback(f"arena:start_attempt:{DUEL_ID}")
    await arena_duel_flow.handle_arena_start_attempt(
        callback,
        arena_start_attempt_re=SimpleNamespace(
            match=lambda value: value.startswith("arena:start_attempt:")
        ),
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
        resolve_arena_accept_access_type=resolve_accept_access,
        accept_arena_duel=unexpected_accept,
        build_question_text=lambda **_kwargs: "arena question",
    )

    response = callback.message.answers[0]
    callbacks = callback_data_list(response.kwargs["reply_markup"])
    assert "Arena-Duell-Limit" in require_text(response.text)
    assert callbacks == ["buy:FRIEND_CHALLENGE_5:duel", "buy:PREMIUM_WEEK:duel", "arena:list"]
    assert "buy:PREMIUM_3_DAYS" not in callbacks


@pytest.mark.parametrize(("context", "expected_text"), PAYWALL_CONTEXT_CASES)
def test_duel_paywall_text_contexts_are_specific(
    context: DuelPaywallContext,
    expected_text: str,
) -> None:
    assert expected_text in resolve_duel_paywall_text(context=context)
