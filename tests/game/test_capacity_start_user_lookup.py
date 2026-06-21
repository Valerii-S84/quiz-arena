from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.handlers.gameplay_flows import play_flow
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


def _callback() -> DummyCallback:
    return DummyCallback(
        data="play",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )


@pytest.mark.asyncio
async def test_menu_start_uses_home_snapshot_path() -> None:
    captured: dict[str, object] = {}

    async def _ensure_home_snapshot(session, *, telegram_user):
        captured["snapshot"] = (session, telegram_user.id)
        return SimpleNamespace(user_id=303, free_energy=7, paid_energy=1)

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
            ensure_home_snapshot=_ensure_home_snapshot,
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

    assert captured["snapshot"] == ("db-session", 101)
    assert captured["start_user_id"] == 303
    assert callback.message.answers[0].text == "energy=7+1;after=18+2"


@pytest.mark.asyncio
async def test_zero_cost_start_keeps_full_home_snapshot_path() -> None:
    captured: dict[str, object] = {}

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
