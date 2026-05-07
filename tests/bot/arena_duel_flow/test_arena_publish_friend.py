from types import SimpleNamespace
from typing import cast

import pytest

from app.bot.handlers import gameplay_callbacks
from app.bot.handlers.gameplay_flows import arena_duel_flow
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeArenaPublishBaselineRequiredError,
    FriendChallengeNotFoundError,
)

from .support import (
    DUEL_ID,
    SessionLocalStub,
    UserServiceStub,
    callback_data_list,
    make_callback,
    require_text,
    start_result,
)


@pytest.mark.asyncio
async def test_arena_publish_friend_publishes_through_service() -> None:
    captured: dict[str, object] = {}

    async def publish_friend(*_args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(duel_id=DUEL_ID, baseline_score=6, baseline_time_ms=48_000)

    callback = make_callback(f"arena:publish_friend:{DUEL_ID}")
    await arena_duel_flow.handle_arena_publish_friend(
        callback,
        arena_publish_friend_re=gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE,
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
        publish_friend_challenge_to_arena=publish_friend,
    )

    response = callback.message.answers[0]
    assert captured["user_id"] == 101
    assert captured["friend_challenge_id"] == DUEL_ID
    assert "🏟 In der Arena veröffentlicht!" in require_text(response.text)
    assert "6/7 · 00:48" in require_text(response.text)
    assert callback_data_list(response.kwargs["reply_markup"]) == [
        f"arena:challenge_friend:{DUEL_ID}",
        "arena:list",
    ]


@pytest.mark.asyncio
async def test_arena_publish_friend_starts_friend_baseline_when_score_is_missing() -> None:
    captured: dict[str, object] = {}

    async def publish_friend(*_args, **kwargs):
        captured["publish"] = kwargs
        raise FriendChallengeArenaPublishBaselineRequiredError

    async def start_friend_round(*_args, **kwargs):
        captured["start"] = kwargs
        return SimpleNamespace(start_result=start_result())

    def build_question_text(**kwargs):
        captured["question"] = kwargs
        return "friend baseline question"

    callback = make_callback(f"arena:publish_friend:{DUEL_ID}")
    await arena_duel_flow.handle_arena_publish_friend(
        callback,
        arena_publish_friend_re=gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE,
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
        publish_friend_challenge_to_arena=publish_friend,
        start_friend_challenge_round=start_friend_round,
        build_question_text=build_question_text,
    )

    publish_call = cast(dict[str, object], captured["publish"])
    start_call = cast(dict[str, object], captured["start"])
    question_call = cast(dict[str, object], captured["question"])
    assert publish_call["user_id"] == 101
    assert start_call["user_id"] == 101
    assert start_call["challenge_id"] == DUEL_ID
    assert question_call["source"] == "FRIEND_CHALLENGE"
    assert callback.message.answers[0].text == "friend baseline question"
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_arena_publish_friend_emits_canonical_friend_publish_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[dict[str, object]] = []

    async def publish_friend(*_args, **_kwargs):
        return SimpleNamespace(duel_id=DUEL_ID, baseline_score=6, baseline_time_ms=48_000)

    async def fake_emit(_session, **kwargs) -> None:
        emitted.append(kwargs)

    monkeypatch.setattr(arena_duel_flow, "emit_arena_analytics_event", fake_emit)

    callback = make_callback(f"arena:publish_friend:{DUEL_ID}")
    await arena_duel_flow.handle_arena_publish_friend(
        callback,
        arena_publish_friend_re=gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE,
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
        publish_friend_challenge_to_arena=publish_friend,
    )

    assert [event["event_type"] for event in emitted] == [
        arena_duel_flow.ARENA_EVENT_ARENA_DUEL_PUBLISHED,
        arena_duel_flow.ARENA_EVENT_FRIEND_DUEL_PUBLISHED_TO_ARENA,
    ]
    assert emitted[0]["payload"] == {
        "user_id": 101,
        "friend_challenge_id": str(DUEL_ID),
        "arena_duel_id": str(DUEL_ID),
        "action": "publish_friend",
        "score": 6,
        "time_ms": 48_000,
    }
    assert emitted[1]["payload"] == {
        "user_id": 101,
        "friend_challenge_id": str(DUEL_ID),
        "arena_duel_id": str(DUEL_ID),
        "score": 6,
        "time_ms": 48_000,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [FriendChallengeAccessError, FriendChallengeNotFoundError])
async def test_arena_publish_friend_maps_invalid_state_to_clean_error(error) -> None:
    async def publish_friend(*_args, **_kwargs):
        raise error

    callback = make_callback(f"arena:publish_friend:{DUEL_ID}")
    await arena_duel_flow.handle_arena_publish_friend(
        callback,
        arena_publish_friend_re=gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE,
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
        publish_friend_challenge_to_arena=publish_friend,
    )

    response = callback.message.answers[0]
    assert "Freundesduell kann noch nicht" in require_text(response.text)
    assert callback_data_list(response.kwargs["reply_markup"]) == ["arena:list"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
