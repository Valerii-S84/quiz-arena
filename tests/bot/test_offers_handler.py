from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.handlers import offers
from app.bot.texts.de import TEXTS_DE
from tests.bot.helpers import DummyCallback, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_offer_dismiss_rejects_missing_required_fields() -> None:
    callback = DummyCallback(data=None, from_user=None)

    await offers.handle_offer_dismiss(callback)  # type: ignore[arg-type]

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_offer_dismiss_rejects_invalid_pattern() -> None:
    callback = DummyCallback(data="offer:dismiss:not-a-number", from_user=SimpleNamespace(id=1))

    await offers.handle_offer_dismiss(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_offer_dismiss_rejects_when_user_not_found(monkeypatch) -> None:
    monkeypatch.setattr(offers, "SessionLocal", DummySessionLocal())

    async def _fake_get_user(session, telegram_user_id: int):
        assert telegram_user_id == 777
        return None

    monkeypatch.setattr(offers.UsersRepo, "get_by_telegram_user_id", _fake_get_user)
    callback = DummyCallback(data="offer:dismiss:10", from_user=SimpleNamespace(id=777))

    await offers.handle_offer_dismiss(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_offer_dismiss_replies_with_success(monkeypatch) -> None:
    monkeypatch.setattr(offers, "SessionLocal", DummySessionLocal())

    async def _fake_get_user(session, telegram_user_id: int):
        return SimpleNamespace(id=42)

    async def _fake_dismiss_offer(session, user_id: int, impression_id: int, now_utc):
        assert user_id == 42
        assert impression_id == 99
        return True

    monkeypatch.setattr(offers.UsersRepo, "get_by_telegram_user_id", _fake_get_user)
    monkeypatch.setattr(offers.OfferService, "dismiss_offer", _fake_dismiss_offer)
    callback = DummyCallback(data="offer:dismiss:99", from_user=SimpleNamespace(id=500))

    await offers.handle_offer_dismiss(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.offer.dismissed"], "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_offer_dismiss_replies_error_when_not_dismissed(
    monkeypatch,
) -> None:
    monkeypatch.setattr(offers, "SessionLocal", DummySessionLocal())

    async def _fake_get_user(session, telegram_user_id: int):
        return SimpleNamespace(id=11)

    async def _fake_dismiss_offer(session, user_id: int, impression_id: int, now_utc):
        return False

    monkeypatch.setattr(offers.UsersRepo, "get_by_telegram_user_id", _fake_get_user)
    monkeypatch.setattr(offers.OfferService, "dismiss_offer", _fake_dismiss_offer)
    callback = DummyCallback(data="offer:dismiss:3", from_user=SimpleNamespace(id=100))

    await offers.handle_offer_dismiss(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]
