from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.handlers import start
from tests.bot.helpers import DummyMessage, DummySessionLocal


class _StartMessage(DummyMessage):
    def __init__(self, *, text: str, from_user: SimpleNamespace, message_id: int = 100) -> None:
        super().__init__()
        self.text = text
        self.from_user = from_user
        self.message_id = message_id


@pytest.mark.asyncio
async def test_handle_start_home_menu_shows_premium_flag(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(
            user_id=8,
            free_energy=12,
            paid_energy=3,
            current_streak=4,
            best_streak=9,
            global_best_streak=27,
            premium_active=True,
        )

    async def _fake_offer(*args, **kwargs):
        return None

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(start.OfferService, "evaluate_and_log_offer", _fake_offer)
    monkeypatch.setattr(
        start.start_flow,
        "get_settings",
        lambda: SimpleNamespace(telegram_home_header_file_id=""),
    )

    message = _StartMessage(
        text="/start",
        from_user=SimpleNamespace(id=2, username="bob", first_name="Bob", language_code="de"),
    )
    await start.handle_start(message)

    assert "⚡ 12/20 | 💎 Premium aktiv" in (message.answers[0].text or "")
