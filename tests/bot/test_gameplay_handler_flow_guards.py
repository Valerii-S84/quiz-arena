from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import TournamentSessionStopNotAllowedError
from tests.bot.helpers import DummyCallback, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_game_stop_with_missing_message_returns_error() -> None:
    callback = DummyCallback(data="game:stop", from_user=SimpleNamespace(id=1))
    callback.message = cast(Any, None)

    await gameplay.handle_game_stop(callback)  # type: ignore[arg-type]

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_game_stop_sends_home_message_via_photo_helper(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def _fake_send_home_message(message, *, text: str) -> None:
        del message
        captured["text"] = text

    monkeypatch.setattr(gameplay, "_send_home_message", _fake_send_home_message)

    callback = DummyCallback(data="game:stop", from_user=SimpleNamespace(id=1))
    await gameplay.handle_game_stop(callback)

    assert captured["text"] == TEXTS_DE["msg.game.stopped"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_game_stop_with_session_payload_marks_session_abandoned(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())
    captured: dict[str, str] = {}

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=77)

    async def _fake_abandon_session(
        session,
        *,
        user_id: int,
        session_id,
        now_utc,
    ) -> None:
        del session, now_utc
        captured["user_id"] = str(user_id)
        captured["session_id"] = str(session_id)

    async def _fake_send_home_message(message, *, text: str) -> None:
        del message
        captured["text"] = text

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "abandon_session", _fake_abandon_session)
    monkeypatch.setattr(gameplay, "_send_home_message", _fake_send_home_message)

    callback = DummyCallback(
        data="game:stop:123e4567-e89b-12d3-a456-426614174000",
        from_user=SimpleNamespace(id=1),
    )
    await gameplay.handle_game_stop(callback)

    assert captured["user_id"] == "77"
    assert captured["session_id"] == "123e4567-e89b-12d3-a456-426614174000"
    assert captured["text"] == TEXTS_DE["msg.game.stopped"]


@pytest.mark.asyncio
async def test_handle_game_stop_with_tournament_session_payload_returns_error(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())
    captured = {"home_called": False}

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=77)

    async def _fake_abandon_session(session, *, user_id: int, session_id, now_utc) -> None:
        del session, user_id, session_id, now_utc
        raise TournamentSessionStopNotAllowedError

    async def _fake_send_home_message(message, *, text: str) -> None:
        del message, text
        captured["home_called"] = True

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "abandon_session", _fake_abandon_session)
    monkeypatch.setattr(gameplay, "_send_home_message", _fake_send_home_message)

    callback = DummyCallback(
        data="game:stop:123e4567-e89b-12d3-a456-426614174000",
        from_user=SimpleNamespace(id=1),
    )
    await gameplay.handle_game_stop(callback)

    assert captured["home_called"] is False
    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_mode_with_missing_data_returns_error() -> None:
    callback = DummyCallback(data=None, from_user=SimpleNamespace(id=1))

    await gameplay.handle_mode(callback)  # type: ignore[arg-type]

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_answer_rejects_missing_callback_fields() -> None:
    callback = DummyCallback(data=None, from_user=None)

    await gameplay.handle_answer(callback)  # type: ignore[arg-type]

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "callback_data", "expected_mode", "expected_source", "expected_key"),
    [
        (
            "handle_play",
            "play",
            "QUICK_MIX_A1A2",
            "MENU",
            "start:play:cb-1",
        ),
        (
            "handle_daily_challenge",
            "daily_challenge",
            "DAILY_CHALLENGE",
            "DAILY_CHALLENGE",
            "start:daily:cb-1",
        ),
    ],
)
async def test_start_handlers_delegate_with_current_bound_dependencies(
    monkeypatch,
    handler_name: str,
    callback_data: str,
    expected_mode: str,
    expected_source: str,
    expected_key: str,
) -> None:
    captured: dict[str, object] = {}
    session_local = object()
    user_onboarding_service = object()
    game_session_service = object()
    offer_service = object()
    channel_bonus_service = object()
    build_question_text = object()

    class DummyOfferLoggingError(RuntimeError):
        pass

    async def _fake_start_mode(callback, **kwargs):
        captured["callback"] = callback
        captured.update(kwargs)

    monkeypatch.setattr(gameplay, "SessionLocal", session_local)
    monkeypatch.setattr(gameplay, "UserOnboardingService", user_onboarding_service)
    monkeypatch.setattr(gameplay, "GameSessionService", game_session_service)
    monkeypatch.setattr(gameplay, "OfferService", offer_service)
    monkeypatch.setattr(gameplay, "OfferLoggingError", DummyOfferLoggingError)
    monkeypatch.setattr(gameplay, "ChannelBonusService", channel_bonus_service)
    monkeypatch.setattr(gameplay, "_build_question_text", build_question_text)
    monkeypatch.setattr(gameplay.play_flow, "start_mode", _fake_start_mode)

    callback = DummyCallback(data=callback_data, from_user=SimpleNamespace(id=1))

    await getattr(gameplay, handler_name)(callback)

    assert captured == {
        "callback": callback,
        "mode_code": expected_mode,
        "source": expected_source,
        "idempotency_key": expected_key,
        "session_local": session_local,
        "user_onboarding_service": user_onboarding_service,
        "game_session_service": game_session_service,
        "offer_service": offer_service,
        "offer_logging_error": DummyOfferLoggingError,
        "channel_bonus_service": channel_bonus_service,
        "build_question_text": build_question_text,
    }


@pytest.mark.asyncio
async def test_handle_mode_delegates_with_current_bound_dependencies(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session_local = object()
    user_onboarding_service = object()
    game_session_service = object()
    offer_service = object()
    channel_bonus_service = object()
    build_question_text = object()

    class DummyOfferLoggingError(RuntimeError):
        pass

    async def _fake_start_mode(callback, **kwargs):
        captured["callback"] = callback
        captured.update(kwargs)

    monkeypatch.setattr(gameplay, "SessionLocal", session_local)
    monkeypatch.setattr(gameplay, "UserOnboardingService", user_onboarding_service)
    monkeypatch.setattr(gameplay, "GameSessionService", game_session_service)
    monkeypatch.setattr(gameplay, "OfferService", offer_service)
    monkeypatch.setattr(gameplay, "OfferLoggingError", DummyOfferLoggingError)
    monkeypatch.setattr(gameplay, "ChannelBonusService", channel_bonus_service)
    monkeypatch.setattr(gameplay, "_build_question_text", build_question_text)
    monkeypatch.setattr(gameplay.play_flow, "start_mode", _fake_start_mode)

    callback = DummyCallback(data="mode:ARTIKEL_SPRINT", from_user=SimpleNamespace(id=1))

    await gameplay.handle_mode(callback)

    assert captured == {
        "callback": callback,
        "mode_code": "ARTIKEL_SPRINT",
        "source": "MENU",
        "idempotency_key": "start:mode:ARTIKEL_SPRINT:cb-1",
        "session_local": session_local,
        "user_onboarding_service": user_onboarding_service,
        "game_session_service": game_session_service,
        "offer_service": offer_service,
        "offer_logging_error": DummyOfferLoggingError,
        "channel_bonus_service": channel_bonus_service,
        "build_question_text": build_question_text,
    }


@pytest.mark.asyncio
async def test_handle_daily_result_delegates_with_current_bound_dependencies(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    session_local = object()
    user_onboarding_service = object()
    game_session_service = object()
    daily_run_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    async def _fake_handle_daily_result_screen(callback, **kwargs):
        captured["callback"] = callback
        captured.update(kwargs)

    monkeypatch.setattr(gameplay, "SessionLocal", session_local)
    monkeypatch.setattr(gameplay, "UserOnboardingService", user_onboarding_service)
    monkeypatch.setattr(gameplay, "GameSessionService", game_session_service)
    monkeypatch.setattr(
        gameplay.daily_result_flow,
        "handle_daily_result_screen",
        _fake_handle_daily_result_screen,
    )

    callback = DummyCallback(
        data=f"daily:result:{daily_run_id}",
        from_user=SimpleNamespace(id=1),
    )

    await gameplay.handle_daily_result(callback)

    assert captured == {
        "callback": callback,
        "daily_run_id": daily_run_id,
        "session_local": session_local,
        "user_onboarding_service": user_onboarding_service,
        "game_session_service": game_session_service,
    }
