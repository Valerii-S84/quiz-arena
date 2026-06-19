from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.bot.handlers.gameplay_flows import answer_flow, play_flow
from tests.bot.gameplay_flow_fixtures import _start_result
from tests.bot.helpers import DummyCallback, DummyMessage

NOW_UTC = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


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


def _callback() -> DummyCallback:
    return DummyCallback(
        data="play",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )


@pytest.mark.asyncio
async def test_menu_start_uses_lightweight_existing_user_lookup() -> None:
    captured: dict[str, Any] = {}

    async def _get_existing_user_id(session, telegram_user_id: int):
        captured["lookup"] = (session, telegram_user_id)
        return 303

    async def _unexpected_home_snapshot(*_args, **_kwargs):
        pytest.fail("existing MENU users should not require a full home snapshot")

    async def _start_session(*args, **kwargs):
        del args
        captured["start_user_id"] = kwargs["user_id"]
        return _start_result()

    callback = _callback()

    await play_flow.start_mode(
        callback,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        idempotency_key="start:menu",
        session_local=_SessionLocal("db-session"),
        user_onboarding_service=SimpleNamespace(
            get_existing_user_id_by_telegram_user_id=_get_existing_user_id,
            ensure_home_snapshot=_unexpected_home_snapshot,
        ),
        game_session_service=SimpleNamespace(start_session=_start_session),
        offer_service=SimpleNamespace(),
        offer_logging_error=RuntimeError,
        channel_bonus_service=SimpleNamespace(),
        build_question_text=lambda **kwargs: (
            f"energy={kwargs['snapshot_free_energy']}+{kwargs['snapshot_paid_energy']};"
            f"after={kwargs['start_result'].energy_free}+{kwargs['start_result'].energy_paid}"
        ),
    )

    assert captured["lookup"] == ("db-session", 101)
    assert captured["start_user_id"] == 303
    assert callback.message.answers[0].text == "energy=0+0;after=18+2"


@pytest.mark.asyncio
async def test_menu_start_falls_back_to_touch_existing_user_before_home_snapshot() -> None:
    captured: dict[str, Any] = {}

    async def _get_existing_user_id(*_args, **_kwargs):
        return None

    async def _touch_existing_user(session, *, telegram_user, now_utc):
        captured["touch"] = (session, telegram_user.id, now_utc)
        return SimpleNamespace(id=404)

    async def _unexpected_home_snapshot(*_args, **_kwargs):
        pytest.fail("touch fallback should resolve the existing user")

    async def _start_session(*args, **kwargs):
        del args
        captured["start_user_id"] = kwargs["user_id"]
        return _start_result()

    await play_flow.start_mode(
        _callback(),
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        idempotency_key="start:fallback",
        session_local=_SessionLocal("db-session"),
        user_onboarding_service=SimpleNamespace(
            get_existing_user_id_by_telegram_user_id=_get_existing_user_id,
            touch_existing_user=_touch_existing_user,
            ensure_home_snapshot=_unexpected_home_snapshot,
        ),
        game_session_service=SimpleNamespace(start_session=_start_session),
        offer_service=SimpleNamespace(),
        offer_logging_error=RuntimeError,
        channel_bonus_service=SimpleNamespace(),
        build_question_text=lambda **_kwargs: "question-text",
    )

    assert captured["touch"][0:2] == ("db-session", 101)
    assert captured["start_user_id"] == 404


@pytest.mark.asyncio
async def test_zero_cost_start_keeps_full_home_snapshot_path() -> None:
    captured: dict[str, Any] = {}

    async def _unexpected_existing_id_lookup(*_args, **_kwargs):
        pytest.fail("zero-cost starts should keep the onboarding snapshot path")

    async def _ensure_home_snapshot(session, *, telegram_user):
        captured["snapshot"] = (session, telegram_user.id)
        return SimpleNamespace(user_id=505, free_energy=9, paid_energy=1)

    async def _start_session(*args, **kwargs):
        del args
        captured["start_user_id"] = kwargs["user_id"]
        return _start_result()

    await play_flow.start_mode(
        _callback(),
        mode_code="DAILY_CHALLENGE",
        source="DAILY_CHALLENGE",
        idempotency_key="start:daily",
        session_local=_SessionLocal("db-session"),
        user_onboarding_service=SimpleNamespace(
            get_existing_user_id_by_telegram_user_id=_unexpected_existing_id_lookup,
            ensure_home_snapshot=_ensure_home_snapshot,
        ),
        game_session_service=SimpleNamespace(start_session=_start_session),
        offer_service=SimpleNamespace(),
        offer_logging_error=RuntimeError,
        channel_bonus_service=SimpleNamespace(),
        build_question_text=lambda **kwargs: f"energy={kwargs['snapshot_free_energy']}",
    )

    assert captured["snapshot"] == ("db-session", 101)
    assert captured["start_user_id"] == 505


@pytest.mark.asyncio
async def test_answer_flow_resolves_existing_user_by_touch_without_home_snapshot() -> None:
    captured: dict[str, Any] = {}

    async def _touch_existing_user(session, *, telegram_user, now_utc):
        captured["touch"] = (session, telegram_user.id, now_utc)
        return SimpleNamespace(id=606)

    async def _unexpected_home_snapshot(*_args, **_kwargs):
        pytest.fail("answer callbacks should use the touch path for existing users")

    context = SimpleNamespace(
        services=SimpleNamespace(
            user_onboarding_service=SimpleNamespace(
                touch_existing_user=_touch_existing_user,
                ensure_home_snapshot=_unexpected_home_snapshot,
            )
        )
    )

    user_id = await answer_flow._resolve_answer_user_id(
        "db-session",
        telegram_user=SimpleNamespace(id=202),
        now_utc=NOW_UTC,
        context=cast(Any, context),
    )

    assert user_id == 606
    assert captured["touch"] == ("db-session", 202, NOW_UTC)
