from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from app.bot.handlers import gameplay_callbacks
from app.bot.handlers.gameplay_flows import (
    arena_duel_flow,
    arena_revanche_delivery,
    arena_revanche_flow,
)
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_LOSS,
    ARENA_ATTEMPT_RESULT_WIN,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_SOURCE,
)
from app.game.arena_duels.errors import (
    ArenaDuelAlreadyAttemptedError,
    ArenaDuelExpiredError,
    ArenaDuelOwnAttemptError,
    ArenaDuelPaymentRequiredError,
)
from app.game.arena_duels.types import (
    ArenaActiveDuelSnapshot,
    ArenaAttemptCompletionResult,
    ArenaAttemptResultLine,
    ArenaBaselineStartResult,
    ArenaDuelSnapshot,
)
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeArenaPublishBaselineRequiredError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.types import SessionQuestionView, StartSessionResult
from tests.bot.helpers import DummyCallback, DummyMessage
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
DUEL_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ATTEMPT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
OPPONENT_ATTEMPT_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


class _SessionLocal:
    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(object())


class _UserService:
    @staticmethod
    async def ensure_home_snapshot(*_args, **_kwargs):
        return SimpleNamespace(user_id=101, free_energy=8, paid_energy=2)

    @staticmethod
    async def get_by_id(_session, user_id: int):
        if user_id == 11:
            return SimpleNamespace(username=None, first_name="Max")
        return None


class _UserServiceWithTelegram:
    @staticmethod
    async def ensure_home_snapshot(*_args, **_kwargs):
        return SimpleNamespace(user_id=101, free_energy=8, paid_energy=2)

    @staticmethod
    async def get_by_id(_session, user_id: int):
        if user_id == 11:
            return SimpleNamespace(
                id=11,
                telegram_user_id=110_000_011,
                username=None,
                first_name="Max",
            )
        if user_id == 101:
            return SimpleNamespace(
                id=101,
                telegram_user_id=101_000_101,
                username="anna",
                first_name="Anna",
            )
        return None


def _active_duel() -> ArenaActiveDuelSnapshot:
    return ArenaActiveDuelSnapshot(
        duel_id=DUEL_ID,
        creator_user_id=11,
        mode_code="QUICK_MIX_A1A2",
        question_ids=tuple(f"q-{index}" for index in range(1, 8)),
        baseline_attempt_id=ATTEMPT_ID,
        score=6,
        time_ms=48_000,
        expires_at=NOW_UTC + timedelta(hours=1),
    )


def _duel_snapshot() -> ArenaDuelSnapshot:
    return ArenaDuelSnapshot(
        duel_id=DUEL_ID,
        creator_user_id=101,
        mode_code="QUICK_MIX_A1A2",
        status=ARENA_DUEL_STATUS_ACTIVE,
        question_ids=tuple(f"q-{index}" for index in range(1, 8)),
        expires_at=NOW_UTC + timedelta(hours=24),
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
        baseline_attempt_id=ATTEMPT_ID,
        baseline_score=6,
        baseline_time_ms=48_000,
    )


def _start_result() -> StartSessionResult:
    return StartSessionResult(
        session=SessionQuestionView(
            session_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            question_id="q-1",
            text="Frage?",
            options=("A", "B", "C", "D"),
            mode_code="QUICK_MIX_A1A2",
            source=ARENA_SOURCE,
            question_number=1,
            total_questions=7,
        ),
        energy_free=0,
        energy_paid=0,
        idempotent_replay=False,
    )


def _callback(data: str) -> DummyCallback:
    return DummyCallback(
        data=data,
        from_user=SimpleNamespace(id=777),
        message=DummyMessage(),
    )


def _callbacks(reply_markup) -> list[str]:
    return [
        button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


def _text(value: str | None) -> str:
    assert value is not None
    return value


@pytest.mark.asyncio
async def test_arena_open_lists_active_duels_with_accept_buttons() -> None:
    async def _list_active(*_args, **_kwargs):
        return (_active_duel(),)

    callback = _callback("duels:arena")
    await arena_duel_flow.handle_arena_open(
        callback,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
        list_active_arena_duels=_list_active,
    )

    response = callback.message.answers[0]
    text = _text(response.text)
    assert "🏟 Offene Arena" in text
    assert "Max" in text
    assert "6/7 · 00:48" in text
    assert _callbacks(response.kwargs["reply_markup"]) == [
        f"arena:accept:{DUEL_ID}",
        "arena:create",
        "duels:menu",
    ]


@pytest.mark.asyncio
async def test_arena_open_uses_empty_state_when_no_active_duels() -> None:
    async def _list_active(*_args, **_kwargs):
        return ()

    callback = _callback("duels:arena")
    await arena_duel_flow.handle_arena_open(
        callback,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
        list_active_arena_duels=_list_active,
    )

    response = callback.message.answers[0]
    assert "Noch gibt es keine aktiven Arena-Duelle." in _text(response.text)
    assert _callbacks(response.kwargs["reply_markup"]) == ["arena:create", "duels:menu"]


@pytest.mark.asyncio
async def test_arena_accept_preview_shows_start_screen() -> None:
    async def _preview(*_args, **_kwargs):
        return _active_duel()

    callback = _callback(f"arena:accept:{DUEL_ID}")
    await arena_duel_flow.handle_arena_accept_preview(
        callback,
        arena_accept_re=SimpleNamespace(match=lambda value: value.startswith("arena:accept:")),
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
        get_arena_duel_accept_preview=_preview,
    )

    response = callback.message.answers[0]
    text = _text(response.text)
    assert "Schlage das Ergebnis von Max." in text
    assert "6/7 · 00:48" in text
    assert _callbacks(response.kwargs["reply_markup"]) == [
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
    async def _preview(*_args, **_kwargs):
        raise error

    callback = _callback(f"arena:accept:{DUEL_ID}")
    await arena_duel_flow.handle_arena_accept_preview(
        callback,
        arena_accept_re=SimpleNamespace(match=lambda value: value.startswith("arena:accept:")),
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
        get_arena_duel_accept_preview=_preview,
    )

    assert expected_text in _text(callback.message.answers[0].text)
    assert _callbacks(callback.message.answers[0].kwargs["reply_markup"]) == expected_callbacks
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_arena_start_create_starts_baseline_question() -> None:
    async def _resolve_create_access(*_args, **_kwargs):
        return "FREE"

    async def _create_baseline(*_args, **_kwargs):
        return ArenaBaselineStartResult(
            duel=_duel_snapshot(),
            baseline_attempt_id=ATTEMPT_ID,
            start_result=_start_result(),
        )

    callback = _callback("arena:start_create")
    await arena_duel_flow.handle_arena_start_create(
        callback,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
        resolve_arena_create_access_type=_resolve_create_access,
        create_arena_duel_baseline=_create_baseline,
        build_question_text=lambda **_kwargs: "arena question",
    )

    response = callback.message.answers[0]
    assert response.text == "arena question"
    assert _callbacks(response.kwargs["reply_markup"]) == [
        "answer:cccccccc-cccc-cccc-cccc-cccccccccccc:0",
        "answer:cccccccc-cccc-cccc-cccc-cccccccccccc:1",
        "answer:cccccccc-cccc-cccc-cccc-cccccccccccc:2",
        "answer:cccccccc-cccc-cccc-cccc-cccccccccccc:3",
        "game:stop:cccccccc-cccc-cccc-cccc-cccccccccccc",
    ]


@pytest.mark.asyncio
async def test_arena_start_create_limit_hit_shows_duel_paywall_without_start() -> None:
    async def _resolve_create_access(*_args, **_kwargs):
        raise ArenaDuelPaymentRequiredError

    async def _unexpected_create_baseline(*_args, **_kwargs):
        pytest.fail("direct arena:start_create must not bypass the duel limit")

    callback = _callback("arena:start_create")
    await arena_duel_flow.handle_arena_start_create(
        callback,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
        resolve_arena_create_access_type=_resolve_create_access,
        create_arena_duel_baseline=_unexpected_create_baseline,
        build_question_text=lambda **_kwargs: "arena question",
    )

    response = callback.message.answers[0]
    assert "Dein heutiges Duell-Limit ist erreicht." in _text(response.text)
    assert _callbacks(response.kwargs["reply_markup"]) == [
        "buy:FRIEND_CHALLENGE_5:duel",
        "buy:PREMIUM_WEEK:duel",
        "arena:list",
    ]


@pytest.mark.asyncio
async def test_arena_start_attempt_maps_session_access_error_to_guard() -> None:
    async def _resolve_accept_access(*_args, **_kwargs):
        return "FREE"

    async def _accept(*_args, **_kwargs):
        raise FriendChallengeAccessError

    callback = _callback(f"arena:start_attempt:{DUEL_ID}")
    await arena_duel_flow.handle_arena_start_attempt(
        callback,
        arena_start_attempt_re=SimpleNamespace(
            match=lambda value: value.startswith("arena:start_attempt:")
        ),
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
        resolve_arena_accept_access_type=_resolve_accept_access,
        accept_arena_duel=_accept,
        build_question_text=lambda **_kwargs: "arena question",
    )

    response = callback.message.answers[0]
    assert "Dieses Duell ist abgelaufen." in _text(response.text)
    assert _callbacks(response.kwargs["reply_markup"]) == ["arena:create", "arena:list"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_arena_start_attempt_limit_hit_shows_duel_paywall_without_accept() -> None:
    async def _resolve_accept_access(*_args, **_kwargs):
        raise ArenaDuelPaymentRequiredError

    async def _unexpected_accept(*_args, **_kwargs):
        pytest.fail("direct arena:start_attempt must not bypass the duel limit")

    callback = _callback(f"arena:start_attempt:{DUEL_ID}")
    await arena_duel_flow.handle_arena_start_attempt(
        callback,
        arena_start_attempt_re=SimpleNamespace(
            match=lambda value: value.startswith("arena:start_attempt:")
        ),
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
        resolve_arena_accept_access_type=_resolve_accept_access,
        accept_arena_duel=_unexpected_accept,
        build_question_text=lambda **_kwargs: "arena question",
    )

    response = callback.message.answers[0]
    callbacks = _callbacks(response.kwargs["reply_markup"])
    assert "Duell-Limit" in _text(response.text)
    assert callbacks == ["buy:FRIEND_CHALLENGE_5:duel", "buy:PREMIUM_WEEK:duel", "arena:list"]
    assert "buy:PREMIUM_3_DAYS" not in callbacks


@pytest.mark.asyncio
async def test_arena_publish_friend_publishes_through_service() -> None:
    captured: dict[str, object] = {}

    async def _publish_friend(*_args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(duel_id=DUEL_ID, baseline_score=6, baseline_time_ms=48_000)

    callback = _callback(f"arena:publish_friend:{DUEL_ID}")
    await arena_duel_flow.handle_arena_publish_friend(
        callback,
        arena_publish_friend_re=gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE,
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
        publish_friend_challenge_to_arena=_publish_friend,
    )

    response = callback.message.answers[0]
    assert captured["user_id"] == 101
    assert captured["friend_challenge_id"] == DUEL_ID
    assert "🏟 In der Arena veröffentlicht!" in _text(response.text)
    assert "6/7 · 00:48" in _text(response.text)
    assert _callbacks(response.kwargs["reply_markup"]) == [
        f"arena:challenge_friend:{DUEL_ID}",
        "arena:list",
    ]


@pytest.mark.asyncio
async def test_arena_publish_friend_starts_friend_baseline_when_score_is_missing() -> None:
    captured: dict[str, object] = {}

    async def _publish_friend(*_args, **kwargs):
        captured["publish"] = kwargs
        raise FriendChallengeArenaPublishBaselineRequiredError

    async def _start_friend_round(*_args, **kwargs):
        captured["start"] = kwargs
        return SimpleNamespace(start_result=_start_result())

    def _build_question_text(**kwargs):
        captured["question"] = kwargs
        return "friend baseline question"

    callback = _callback(f"arena:publish_friend:{DUEL_ID}")
    await arena_duel_flow.handle_arena_publish_friend(
        callback,
        arena_publish_friend_re=gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE,
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
        publish_friend_challenge_to_arena=_publish_friend,
        start_friend_challenge_round=_start_friend_round,
        build_question_text=_build_question_text,
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

    async def _publish_friend(*_args, **_kwargs):
        return SimpleNamespace(
            duel_id=DUEL_ID,
            baseline_score=6,
            baseline_time_ms=48_000,
        )

    async def _fake_emit(_session, **kwargs) -> None:
        emitted.append(kwargs)

    monkeypatch.setattr(arena_duel_flow, "emit_arena_analytics_event", _fake_emit)

    callback = _callback(f"arena:publish_friend:{DUEL_ID}")
    await arena_duel_flow.handle_arena_publish_friend(
        callback,
        arena_publish_friend_re=gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE,
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
        publish_friend_challenge_to_arena=_publish_friend,
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
    async def _publish_friend(*_args, **_kwargs):
        raise error

    callback = _callback(f"arena:publish_friend:{DUEL_ID}")
    await arena_duel_flow.handle_arena_publish_friend(
        callback,
        arena_publish_friend_re=SimpleNamespace(
            match=lambda value: value.startswith("arena:publish_friend:")
        ),
        parse_uuid_callback=lambda **_kwargs: DUEL_ID,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
        publish_friend_challenge_to_arena=_publish_friend,
    )

    response = callback.message.answers[0]
    assert "Freundesduell kann noch nicht" in _text(response.text)
    assert _callbacks(response.kwargs["reply_markup"]) == ["arena:list"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_arena_revanche_confirm_shows_confirmation_without_push() -> None:
    async def _load_context(*_args, **_kwargs):
        return SimpleNamespace(receiver_user_id=11)

    callback = _callback(f"arena:revanche:{OPPONENT_ATTEMPT_ID}")
    await arena_revanche_flow.handle_arena_revanche_confirm(
        callback,
        arena_revanche_re=gameplay_callbacks.ARENA_REVANCHE_RE,
        parse_uuid_callback=lambda **_kwargs: OPPONENT_ATTEMPT_ID,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserServiceWithTelegram,
        load_arena_revanche_context=_load_context,
    )

    response = callback.message.answers[0]
    assert "Max erhält genau eine Nachricht." in _text(response.text)
    assert _callbacks(response.kwargs["reply_markup"]) == [
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

    async def _prepare(*_args, **_kwargs):
        return SimpleNamespace(
            already_sent=False,
            context=SimpleNamespace(receiver_user_id=11),
            challenge=SimpleNamespace(challenge_id=challenge_id),
        )

    async def _record(*_args, **kwargs):
        recorded.append(kwargs)
        return True

    async def _cleanup(*_args, **_kwargs):
        pytest.fail("successful Revanche push must not cleanup")

    async def _lock(*_args, **_kwargs):
        return None

    async def _is_sent(*_args, **_kwargs):
        return False

    monkeypatch.setattr(arena_revanche_delivery, "lock_arena_revanche_delivery", _lock)
    monkeypatch.setattr(arena_revanche_delivery, "is_arena_revanche_sent", _is_sent)

    callback = _callback(f"arena:revanche_send:{OPPONENT_ATTEMPT_ID}")
    await arena_revanche_flow.handle_arena_revanche_send(
        callback,
        arena_revanche_send_re=gameplay_callbacks.ARENA_REVANCHE_SEND_RE,
        parse_uuid_callback=lambda **_kwargs: OPPONENT_ATTEMPT_ID,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserServiceWithTelegram,
        prepare_arena_revanche_request=_prepare,
        record_arena_revanche_sent=_record,
        cleanup_arena_revanche_request=_cleanup,
    )

    assert len(callback.bot.sent_messages) == 1
    sent = callback.bot.sent_messages[0]
    assert sent["chat_id"] == 110_000_011
    assert "@anna fordert dich zur Revanche heraus." in str(sent["text"])
    assert _callbacks(sent["reply_markup"]) == [f"friend:next:{challenge_id}", "home:open"]
    recorded_request = cast(Any, recorded[0]["request"])
    assert recorded_request.challenge.challenge_id == challenge_id
    assert "Revanche gesendet." in _text(callback.message.answers[0].text)
    assert _callbacks(callback.message.answers[0].kwargs["reply_markup"]) == ["arena:list"]


@pytest.mark.asyncio
async def test_arena_revanche_send_dedupes_existing_request_without_push() -> None:
    async def _prepare(*_args, **_kwargs):
        return SimpleNamespace(
            already_sent=True,
            context=SimpleNamespace(receiver_user_id=11),
            challenge=None,
        )

    async def _unexpected_record(*_args, **_kwargs):
        pytest.fail("duplicate Revanche tap must not record or push again")

    async def _unexpected_cleanup(*_args, **_kwargs):
        pytest.fail("duplicate Revanche tap must not cleanup")

    callback = _callback(f"arena:revanche_send:{OPPONENT_ATTEMPT_ID}")
    await arena_revanche_flow.handle_arena_revanche_send(
        callback,
        arena_revanche_send_re=gameplay_callbacks.ARENA_REVANCHE_SEND_RE,
        parse_uuid_callback=lambda **_kwargs: OPPONENT_ATTEMPT_ID,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserServiceWithTelegram,
        prepare_arena_revanche_request=_prepare,
        record_arena_revanche_sent=_unexpected_record,
        cleanup_arena_revanche_request=_unexpected_cleanup,
    )

    assert callback.bot.sent_messages == []
    assert "Revanche gesendet." in _text(callback.message.answers[0].text)


@pytest.mark.asyncio
async def test_arena_completion_published_result_screen() -> None:
    callback = _callback("answer")
    completion = ArenaAttemptCompletionResult(
        duel=_duel_snapshot(),
        completed_attempt=ArenaAttemptResultLine(
            user_id=101,
            score=6,
            time_ms=48_000,
            result="BASELINE",
        ),
    )

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
    )

    response = callback.message.answers[0]
    text = _text(response.text)
    assert "Dein Arena-Duell ist aktiv!" in text
    assert "6/7 · 00:48" in text
    assert _callbacks(response.kwargs["reply_markup"]) == [
        f"arena:challenge_friend:{DUEL_ID}",
        "arena:list",
    ]


@pytest.mark.asyncio
async def test_arena_completion_published_result_offers_same_duel_friend_challenge() -> None:
    callback = _callback("answer")
    completion = ArenaAttemptCompletionResult(
        duel=_duel_snapshot(),
        completed_attempt=ArenaAttemptResultLine(
            user_id=101,
            score=6,
            time_ms=48_000,
            result="BASELINE",
        ),
    )

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
    )

    callbacks = _callbacks(callback.message.answers[0].kwargs["reply_markup"])
    assert f"arena:challenge_friend:{DUEL_ID}" in callbacks
    assert "duels:friend" not in callbacks


@pytest.mark.asyncio
async def test_arena_completion_without_completed_attempt_is_silent() -> None:
    callback = _callback("answer")
    completion = ArenaAttemptCompletionResult(duel=_duel_snapshot())

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
    )

    assert callback.message.answers == []


@pytest.mark.asyncio
async def test_arena_completion_challenger_result_screen() -> None:
    callback = _callback("answer")
    completion = ArenaAttemptCompletionResult(
        duel=_duel_snapshot(),
        completed_attempt=ArenaAttemptResultLine(
            user_id=101,
            score=7,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
        opponent_attempt=ArenaAttemptResultLine(
            user_id=11,
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
        ),
    )

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
    )

    response = callback.message.answers[0]
    text = _text(response.text)
    assert "🎉 Gewonnen!" in text
    assert "Du hast das Ergebnis von Max geschlagen." in text
    assert "7/7 · 00:52" in text
    assert "6/7 · 00:48" in text
    assert _callbacks(response.kwargs["reply_markup"]) == ["arena:create", "arena:list"]


@pytest.mark.asyncio
async def test_arena_completion_challenger_win_result_has_revanche() -> None:
    callback = _callback("answer")
    completion = ArenaAttemptCompletionResult(
        duel=_duel_snapshot(),
        completed_attempt=ArenaAttemptResultLine(
            user_id=101,
            score=7,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
        opponent_attempt=ArenaAttemptResultLine(
            user_id=11,
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
            attempt_id=OPPONENT_ATTEMPT_ID,
        ),
    )

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
    )

    assert _callbacks(callback.message.answers[0].kwargs["reply_markup"]) == [
        f"arena:revanche:{OPPONENT_ATTEMPT_ID}",
        "arena:list",
    ]


@pytest.mark.asyncio
async def test_arena_completion_challenger_loss_result_has_next_actions() -> None:
    callback = _callback("answer")
    completion = ArenaAttemptCompletionResult(
        duel=_duel_snapshot(),
        completed_attempt=ArenaAttemptResultLine(
            user_id=101,
            score=5,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
        ),
        opponent_attempt=ArenaAttemptResultLine(
            user_id=11,
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
    )

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
    )

    response = callback.message.answers[0]
    assert "Max bleibt vorne." in _text(response.text)
    assert _callbacks(response.kwargs["reply_markup"]) == ["arena:create", "arena:list"]


@pytest.mark.asyncio
async def test_arena_completion_close_loss_result_has_revanche() -> None:
    callback = _callback("answer")
    completion = ArenaAttemptCompletionResult(
        duel=_duel_snapshot(),
        completed_attempt=ArenaAttemptResultLine(
            user_id=101,
            score=6,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
        ),
        opponent_attempt=ArenaAttemptResultLine(
            user_id=11,
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
            attempt_id=OPPONENT_ATTEMPT_ID,
        ),
    )

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=_SessionLocal(),
        user_onboarding_service=_UserService,
    )

    assert "Knapp verloren." in _text(callback.message.answers[0].text)
    assert _callbacks(callback.message.answers[0].kwargs["reply_markup"]) == [
        f"arena:revanche:{OPPONENT_ATTEMPT_ID}",
        "buy:FRIEND_CHALLENGE_5:duel",
        "buy:PREMIUM_WEEK:duel",
        "arena:list",
    ]
