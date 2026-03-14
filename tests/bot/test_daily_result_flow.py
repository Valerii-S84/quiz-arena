from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import daily_result_flow
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import SessionNotFoundError
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
async def test_handle_daily_result_screen_rejects_invalid_callback_context() -> None:
    callback = DummyCallback(data="daily:result:x", from_user=None, message=DummyMessage())

    await daily_result_flow.handle_daily_result_screen(
        callback,
        daily_run_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        session_local=SimpleNamespace(),
        user_onboarding_service=SimpleNamespace(),
        game_session_service=SimpleNamespace(),
    )

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_daily_result_screen_shows_not_found_for_missing_run() -> None:
    async def _fake_snapshot(_session, *, telegram_user):
        del _session
        assert telegram_user.id == 21
        return SimpleNamespace(user_id=7, current_streak=2)

    async def _fake_summary(*args, **kwargs):
        del args, kwargs
        raise SessionNotFoundError

    callback = DummyCallback(
        data="daily:result:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=21),
        message=DummyMessage(),
    )
    await daily_result_flow.handle_daily_result_screen(
        callback,
        daily_run_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        session_local=_SessionLocal(object()),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_snapshot),
        game_session_service=SimpleNamespace(get_daily_run_summary=_fake_summary),
    )

    assert callback.message.answers[0].text == TEXTS_DE["msg.game.session.not_found"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_daily_result_screen_shows_used_when_summary_not_completed() -> None:
    async def _fake_snapshot(_session, *, telegram_user):
        del _session
        assert telegram_user.id == 21
        return SimpleNamespace(user_id=7, current_streak=2)

    async def _fake_summary(_session, *, user_id: int, daily_run_id):
        del _session
        assert user_id == 7
        assert daily_run_id == UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        return SimpleNamespace(status="IN_PROGRESS")

    callback = DummyCallback(
        data="daily:result:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=21),
        message=DummyMessage(),
    )
    await daily_result_flow.handle_daily_result_screen(
        callback,
        daily_run_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        session_local=_SessionLocal(object()),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_snapshot),
        game_session_service=SimpleNamespace(get_daily_run_summary=_fake_summary),
    )

    assert callback.message.answers[0].text == TEXTS_DE["msg.daily.challenge.used"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_daily_result_screen_renders_completed_summary_with_streak() -> None:
    session = object()
    calls: dict[str, object] = {}
    daily_run_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    async def _fake_snapshot(_session, *, telegram_user):
        assert _session is session
        assert telegram_user.id == 21
        return SimpleNamespace(user_id=7, current_streak=3)

    async def _fake_summary(_session, *, user_id: int, daily_run_id):
        assert _session is session
        calls["user_id"] = user_id
        calls["daily_run_id"] = daily_run_id
        return SimpleNamespace(
            status="COMPLETED",
            score=4,
            total_questions=5,
            daily_run_id=daily_run_id,
        )

    callback = DummyCallback(
        data=f"daily:result:{daily_run_id}",
        from_user=SimpleNamespace(id=21),
        message=DummyMessage(),
    )
    await daily_result_flow.handle_daily_result_screen(
        callback,
        daily_run_id=daily_run_id,
        session_local=_SessionLocal(session),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_snapshot),
        game_session_service=SimpleNamespace(get_daily_run_summary=_fake_summary),
    )

    answer = callback.message.answers[0]
    assert calls == {"user_id": 7, "daily_run_id": daily_run_id}
    assert answer.text == TEXTS_DE["msg.daily.result.summary.with_streak"].format(
        score=4,
        total=5,
        streak=3,
    )
    callbacks = [
        button.callback_data
        for row in answer.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == [f"daily:result:{daily_run_id}", "home:open"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_daily_result_screen_renders_completed_summary_without_streak() -> None:
    daily_run_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    async def _fake_snapshot(_session, *, telegram_user):
        del _session
        assert telegram_user.id == 21
        return SimpleNamespace(user_id=7, current_streak=0)

    async def _fake_summary(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(
            status="COMPLETED",
            score=2,
            total_questions=5,
            daily_run_id=daily_run_id,
        )

    callback = DummyCallback(
        data=f"daily:result:{daily_run_id}",
        from_user=SimpleNamespace(id=21),
        message=DummyMessage(),
    )
    await daily_result_flow.handle_daily_result_screen(
        callback,
        daily_run_id=daily_run_id,
        session_local=_SessionLocal(object()),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_snapshot),
        game_session_service=SimpleNamespace(get_daily_run_summary=_fake_summary),
    )

    assert callback.message.answers[0].text == TEXTS_DE[
        "msg.daily.result.summary.no_streak"
    ].format(
        score=2,
        total=5,
    )
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
