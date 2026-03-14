from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import play_flow
from app.game.sessions.errors import EnergyInsufficientError
from app.game.sessions.types import AnswerSessionResult
from tests.bot.gameplay_flow_fixtures import _start_result
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


def _snapshot() -> SimpleNamespace:
    return SimpleNamespace(user_id=101, free_energy=18, paid_energy=2)


def _callback() -> DummyCallback:
    return DummyCallback(data="play", from_user=SimpleNamespace(id=101), message=DummyMessage())


def _answer_result() -> AnswerSessionResult:
    return AnswerSessionResult(
        session_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        question_id="q-1",
        is_correct=True,
        current_streak=3,
        best_streak=5,
        idempotent_replay=False,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        next_preferred_level="A2",
    )


@pytest.mark.asyncio
async def test_continue_regular_mode_after_answer_sends_next_question() -> None:
    async def _ensure_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return _snapshot()

    async def _start_session(*args, **kwargs):
        del args, kwargs
        return _start_result()

    callback = _callback()

    await play_flow.continue_regular_mode_after_answer(
        callback,
        result=_answer_result(),
        now_utc=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
        session_local=_SessionLocal(object()),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_ensure_home_snapshot),
        game_session_service=SimpleNamespace(start_session=_start_session),
        offer_service=SimpleNamespace(),
        offer_logging_error=RuntimeError,
        channel_bonus_service=SimpleNamespace(),
        build_question_text=lambda **kwargs: "next-question",
    )

    assert callback.message.answers[0].text == "next-question"
    assert callback.message.answers[0].kwargs["parse_mode"] == "HTML"
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_continue_regular_mode_after_answer_handles_energy_insufficient() -> None:
    captured: list[dict[str, object]] = []

    async def _ensure_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return _snapshot()

    async def _start_session(*args, **kwargs):
        del args, kwargs
        raise EnergyInsufficientError()

    async def _handle_energy(callback_obj, **kwargs):
        del callback_obj
        captured.append(kwargs)

    callback = _callback()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(play_flow, "handle_energy_insufficient", _handle_energy)

        await play_flow.continue_regular_mode_after_answer(
            callback,
            result=_answer_result(),
            now_utc=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
            session_local=_SessionLocal("db-session"),
            user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_ensure_home_snapshot),
            game_session_service=SimpleNamespace(start_session=_start_session),
            offer_service=SimpleNamespace(),
            offer_logging_error=RuntimeError,
            channel_bonus_service=SimpleNamespace(),
            build_question_text=lambda **kwargs: "unused",
        )

    assert captured[0]["user_id"] == 101
    assert captured[0]["offer_idempotency_key"] == "offer:energy:auto:cb-1"
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
