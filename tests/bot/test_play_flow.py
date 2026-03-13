from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import play_flow
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    DailyChallengeAlreadyPlayedError,
    EnergyInsufficientError,
    ModeLockedError,
)
from app.game.sessions.types import FriendChallengeRoundStartResult
from tests.bot.gameplay_flow_fixtures import _challenge_snapshot, _start_result
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


def _build_callback(*, with_message: bool = True, with_user: bool = True) -> DummyCallback:
    callback = DummyCallback(
        data="play",
        from_user=SimpleNamespace(id=101) if with_user else None,
        message=DummyMessage() if with_message else DummyMessage(),
    )
    if not with_message:
        callback.message = None
    return callback


def _services_for_start(*, start_session):
    async def _ensure_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return _snapshot()

    return (
        SimpleNamespace(ensure_home_snapshot=_ensure_home_snapshot),
        SimpleNamespace(start_session=start_session),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("with_message", "with_user"), [(False, True), (True, False)])
async def test_start_mode_shows_system_error_when_callback_is_incomplete(
    with_message: bool,
    with_user: bool,
) -> None:
    callback = _build_callback(with_message=with_message, with_user=with_user)

    await play_flow.start_mode(
        callback,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        idempotency_key="start:1",
        session_local=_SessionLocal(object()),
        user_onboarding_service=SimpleNamespace(),
        game_session_service=SimpleNamespace(),
        offer_service=SimpleNamespace(),
        offer_logging_error=RuntimeError,
        channel_bonus_service=SimpleNamespace(),
        trg_locked_mode_click="locked",
        build_question_text=lambda **kwargs: str(kwargs),
    )

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_start_mode_sends_first_question_for_happy_path() -> None:
    async def _start_session(*args, **kwargs):
        del args, kwargs
        return _start_result()

    user_onboarding_service, game_session_service = _services_for_start(
        start_session=_start_session
    )
    callback = _build_callback()

    await play_flow.start_mode(
        callback,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        idempotency_key="start:1",
        session_local=_SessionLocal(object()),
        user_onboarding_service=user_onboarding_service,
        game_session_service=game_session_service,
        offer_service=SimpleNamespace(),
        offer_logging_error=RuntimeError,
        channel_bonus_service=SimpleNamespace(),
        trg_locked_mode_click="locked",
        build_question_text=lambda **kwargs: "question-text",
    )

    assert callback.message.answers[0].text == "question-text"
    assert callback.message.answers[0].kwargs["parse_mode"] == "HTML"
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_start_mode_handles_locked_mode_with_offer() -> None:
    async def _start_session(*args, **kwargs):
        del args, kwargs
        raise ModeLockedError()

    async def _evaluate_offer(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(
            text_key="msg.locked.mode", impression_id="imp", cta_product_codes=()
        )

    user_onboarding_service, game_session_service = _services_for_start(
        start_session=_start_session
    )
    callback = _build_callback()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            play_flow, "build_offer_keyboard", lambda selection: {"offer": selection.impression_id}
        )

        await play_flow.start_mode(
            callback,
            mode_code="ARTIKEL_SPRINT",
            source="MENU",
            idempotency_key="start:2",
            session_local=_SessionLocal(object()),
            user_onboarding_service=user_onboarding_service,
            game_session_service=game_session_service,
            offer_service=SimpleNamespace(evaluate_and_log_offer=_evaluate_offer),
            offer_logging_error=RuntimeError,
            channel_bonus_service=SimpleNamespace(),
            trg_locked_mode_click="locked",
            build_question_text=lambda **kwargs: "unused",
        )

    assert callback.message.answers[0].text == TEXTS_DE["msg.locked.mode"]
    assert callback.message.answers[0].kwargs["reply_markup"] == {"offer": "imp"}
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_start_mode_handles_locked_mode_when_offer_logging_fails() -> None:
    async def _start_session(*args, **kwargs):
        del args, kwargs
        raise ModeLockedError()

    async def _evaluate_offer(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("offer logging failed")

    user_onboarding_service, game_session_service = _services_for_start(
        start_session=_start_session
    )
    callback = _build_callback()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(play_flow, "build_home_keyboard", lambda: {"home": True})

        await play_flow.start_mode(
            callback,
            mode_code="ARTIKEL_SPRINT",
            source="MENU",
            idempotency_key="start:3",
            session_local=_SessionLocal(object()),
            user_onboarding_service=user_onboarding_service,
            game_session_service=game_session_service,
            offer_service=SimpleNamespace(evaluate_and_log_offer=_evaluate_offer),
            offer_logging_error=RuntimeError,
            channel_bonus_service=SimpleNamespace(),
            trg_locked_mode_click="locked",
            build_question_text=lambda **kwargs: "unused",
        )

    assert callback.message.answers[0].text == TEXTS_DE["msg.locked.mode"]
    assert callback.message.answers[0].kwargs["reply_markup"] == {"home": True}


@pytest.mark.asyncio
async def test_start_mode_delegates_energy_insufficient_handling() -> None:
    captured: list[dict[str, object]] = []

    async def _start_session(*args, **kwargs):
        del args, kwargs
        raise EnergyInsufficientError()

    async def _handle_energy(callback_obj, **kwargs):
        del callback_obj
        captured.append(kwargs)

    user_onboarding_service, game_session_service = _services_for_start(
        start_session=_start_session
    )
    callback = _build_callback()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(play_flow, "handle_energy_insufficient", _handle_energy)

        await play_flow.start_mode(
            callback,
            mode_code="QUICK_MIX_A1A2",
            source="MENU",
            idempotency_key="start:4",
            session_local=_SessionLocal("db-session"),
            user_onboarding_service=user_onboarding_service,
            game_session_service=game_session_service,
            offer_service=SimpleNamespace(),
            offer_logging_error=RuntimeError,
            channel_bonus_service=SimpleNamespace(),
            trg_locked_mode_click="locked",
            build_question_text=lambda **kwargs: "unused",
        )

    assert captured[0]["user_id"] == 101
    assert captured[0]["offer_idempotency_key"] == "offer:energy:cb-1"
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_start_mode_handles_daily_challenge_already_played() -> None:
    async def _start_session(*args, **kwargs):
        del args, kwargs
        raise DailyChallengeAlreadyPlayedError()

    user_onboarding_service, game_session_service = _services_for_start(
        start_session=_start_session
    )
    callback = _build_callback()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(play_flow, "build_home_keyboard", lambda: {"home": True})

        await play_flow.start_mode(
            callback,
            mode_code="DAILY_CHALLENGE",
            source="DAILY_CHALLENGE",
            idempotency_key="start:5",
            session_local=_SessionLocal(object()),
            user_onboarding_service=user_onboarding_service,
            game_session_service=game_session_service,
            offer_service=SimpleNamespace(),
            offer_logging_error=RuntimeError,
            channel_bonus_service=SimpleNamespace(),
            trg_locked_mode_click="locked",
            build_question_text=lambda **kwargs: "unused",
        )

    assert callback.message.answers[0].text == TEXTS_DE["msg.daily.challenge.used"]
    assert callback.message.answers[0].kwargs["reply_markup"] == {"home": True}


@pytest.mark.asyncio
async def test_send_friend_round_question_sends_tournament_question() -> None:
    callback = _build_callback()
    round_start = FriendChallengeRoundStartResult(
        snapshot=_challenge_snapshot(),
        start_result=_start_result(),
        waiting_for_opponent=False,
    )
    round_start.snapshot.tournament_match_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    await play_flow.send_friend_round_question(
        callback,
        snapshot_free_energy=18,
        snapshot_paid_energy=2,
        round_start=round_start,
        build_question_text=lambda **kwargs: "friend-question",
    )

    assert callback.message.answers[0].text == "friend-question"
    assert callback.message.answers[0].kwargs["parse_mode"] == "HTML"
    assert len(callback.message.answers[0].kwargs["reply_markup"].inline_keyboard) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(("with_message", "with_start_result"), [(False, True), (True, False)])
async def test_send_friend_round_question_returns_early_for_missing_inputs(
    with_message: bool,
    with_start_result: bool,
) -> None:
    callback = _build_callback(with_message=with_message)
    round_start = FriendChallengeRoundStartResult(
        snapshot=_challenge_snapshot(),
        start_result=_start_result() if with_start_result else None,
        waiting_for_opponent=False,
    )

    await play_flow.send_friend_round_question(
        callback,
        snapshot_free_energy=18,
        snapshot_paid_energy=2,
        round_start=round_start,
        build_question_text=lambda **kwargs: "unused",
    )

    if callback.message is not None:
        assert callback.message.answers == []
