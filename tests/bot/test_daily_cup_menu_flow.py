from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.bot.handlers.gameplay_flows import daily_cup_menu_flow
from app.bot.texts.de import TEXTS_DE
from app.game.tournaments.daily_cup_user_status import (
    DailyCupUserStatus,
    DailyCupUserStatusSnapshot,
)
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
async def test_menu_flow_shows_no_tournament_message_when_no_cup(monkeypatch) -> None:
    daily_cup_menu_flow._last_opened_at_by_user_id.clear()
    callback = DummyCallback(
        data="daily:cup:menu",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=42)

    async def _fake_status(session, *, user_id, now_utc):
        del session, user_id, now_utc
        return DailyCupUserStatusSnapshot(
            status=DailyCupUserStatus.NO_TOURNAMENT,
            tournament=None,
        )

    monkeypatch.setattr(daily_cup_menu_flow, "get_daily_cup_status_for_user", _fake_status)

    await daily_cup_menu_flow.handle_daily_cup_menu(
        callback,
        session_local=DummySessionLocal(),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_home_snapshot),
        tournament_service=SimpleNamespace(),
        users_repo=SimpleNamespace(),
    )

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.daily_cup.no_tournament"]


@pytest.mark.asyncio
async def test_menu_flow_shows_not_participant_message_when_cup_is_running(monkeypatch) -> None:
    daily_cup_menu_flow._last_opened_at_by_user_id.clear()
    callback = DummyCallback(
        data="daily:cup:menu",
        from_user=SimpleNamespace(id=202),
        message=DummyMessage(),
    )

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=77)

    async def _fake_status(session, *, user_id, now_utc):
        del session, user_id, now_utc
        return DailyCupUserStatusSnapshot(
            status=DailyCupUserStatus.NOT_PARTICIPANT,
            tournament=SimpleNamespace(id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        )

    monkeypatch.setattr(daily_cup_menu_flow, "get_daily_cup_status_for_user", _fake_status)

    await daily_cup_menu_flow.handle_daily_cup_menu(
        callback,
        session_local=DummySessionLocal(),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_home_snapshot),
        tournament_service=SimpleNamespace(),
        users_repo=SimpleNamespace(),
    )

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.daily_cup.not_participant"]


@pytest.mark.asyncio
async def test_menu_flow_uses_cooldown_to_prevent_duplicate_spam(monkeypatch) -> None:
    daily_cup_menu_flow._last_opened_at_by_user_id.clear()
    callback = DummyCallback(
        data="daily:cup:menu",
        from_user=SimpleNamespace(id=303),
        message=DummyMessage(),
    )

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=99)

    async def _fake_status(session, *, user_id, now_utc):
        del session, user_id, now_utc
        return DailyCupUserStatusSnapshot(
            status=DailyCupUserStatus.NO_TOURNAMENT,
            tournament=None,
        )

    fixed_now = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    monkeypatch.setattr(daily_cup_menu_flow, "get_daily_cup_status_for_user", _fake_status)
    monkeypatch.setattr(daily_cup_menu_flow, "datetime", _FixedDateTime)

    kwargs = {
        "session_local": DummySessionLocal(),
        "user_onboarding_service": SimpleNamespace(ensure_home_snapshot=_fake_home_snapshot),
        "tournament_service": SimpleNamespace(),
        "users_repo": SimpleNamespace(),
    }
    await daily_cup_menu_flow.handle_daily_cup_menu(callback, **kwargs)
    await daily_cup_menu_flow.handle_daily_cup_menu(callback, **kwargs)

    assert len(callback.message.answers) == 1
    assert callback.answer_calls[-1]["text"] == TEXTS_DE["msg.daily_cup.menu.already_open"]
