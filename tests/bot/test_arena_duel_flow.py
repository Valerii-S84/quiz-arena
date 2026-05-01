from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import arena_duel_flow
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
)
from app.game.arena_duels.types import (
    ArenaActiveDuelSnapshot,
    ArenaAttemptCompletionResult,
    ArenaAttemptResultLine,
    ArenaBaselineStartResult,
    ArenaDuelSnapshot,
)
from app.game.sessions.errors import FriendChallengeAccessError
from app.game.sessions.types import SessionQuestionView, StartSessionResult
from tests.bot.helpers import DummyCallback, DummyMessage
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
DUEL_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ATTEMPT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


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
    ("error", "expected_text"),
    [
        (ArenaDuelOwnAttemptError, "Das ist dein eigenes Arena-Duell."),
        (ArenaDuelAlreadyAttemptedError, "Du hast dieses Arena-Duell bereits gespielt."),
        (ArenaDuelExpiredError, "Dieses Duell ist abgelaufen."),
    ],
)
async def test_arena_accept_preview_maps_guards_to_clean_messages(error, expected_text) -> None:
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
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_arena_start_create_starts_baseline_question() -> None:
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
async def test_arena_start_attempt_maps_session_access_error_to_guard() -> None:
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
        accept_arena_duel=_accept,
        build_question_text=lambda **_kwargs: "arena question",
    )

    assert "Dieses Duell ist abgelaufen." in _text(callback.message.answers[0].text)
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


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
        "arena:list",
        "duels:friend",
        "arena:create",
    ]


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
