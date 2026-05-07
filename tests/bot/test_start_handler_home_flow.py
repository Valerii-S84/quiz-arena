from __future__ import annotations

from tests.bot.start_handler_flow_support import (
    TEXTS_DE,
    DummySessionLocal,
    OfferSelection,
    SimpleNamespace,
    _StartMessage,
    _StartMessageWithPhotoGuard,
)
from tests.bot.start_handler_flow_support import (  # noqa: F401
    _stub_start_runtime as _stub_start_runtime,
)
from tests.bot.start_handler_flow_support import pytest, start

pytestmark = pytest.mark.usefixtures("_stub_start_runtime")


@pytest.mark.asyncio
async def test_handle_start_sends_home_and_offer_when_available(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(
            user_id=8,
            free_energy=8,
            paid_energy=3,
            current_streak=4,
            best_streak=9,
            global_best_streak=27,
        )

    async def _fake_offer(*args, **kwargs):
        return OfferSelection(
            impression_id=1,
            offer_code="ENERGY_10",
            trigger_code="TRG_ENERGY_LOW",
            priority=100,
            text_key="msg.offer.energy.low",
            cta_product_codes=("ENERGY_10",),
            idempotent_replay=False,
        )

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(start.OfferService, "evaluate_and_log_offer", _fake_offer)

    message = _StartMessage(
        text="/start",
        from_user=SimpleNamespace(id=2, username="bob", first_name="Bob", language_code="de"),
    )
    await start.handle_start(message)

    assert len(message.answers) == 2
    assert "Serie: 4 | Beste: 9 | 🏆 Rekord: 27" in (message.answers[0].text or "")
    assert "💎" not in (message.answers[0].text or "")
    assert message.answers[1].text == TEXTS_DE["msg.offer.energy.low"]


@pytest.mark.asyncio
async def test_handle_start_home_menu_does_not_send_photo(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(user_id=8, free_energy=8, paid_energy=3, current_streak=4)

    async def _fake_offer(*args, **kwargs):
        return None

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(start.OfferService, "evaluate_and_log_offer", _fake_offer)
    monkeypatch.setattr(
        start.start_flow,
        "get_settings",
        lambda: SimpleNamespace(telegram_home_header_file_id=""),
    )

    message = _StartMessageWithPhotoGuard(
        text="/start",
        from_user=SimpleNamespace(id=2, username="bob", first_name="Bob", language_code="de"),
    )
    await start.handle_start(message)

    assert message.photo_calls == 0


@pytest.mark.asyncio
async def test_handle_start_home_menu_shows_zero_streak_without_crashing(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(
            user_id=8,
            free_energy=8,
            paid_energy=3,
            current_streak=0,
            best_streak=0,
            global_best_streak=7,
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

    home_text = message.answers[0].text or ""
    assert "Serie: 0 | Beste: 0 | 🏆 Rekord: 7" in home_text
    assert "⚡ 8/10" in home_text


@pytest.mark.asyncio
async def test_handle_start_home_menu_sends_photo_when_file_id_configured(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(user_id=8, free_energy=8, paid_energy=3, current_streak=4)

    async def _fake_offer(*args, **kwargs):
        return None

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(start.OfferService, "evaluate_and_log_offer", _fake_offer)
    monkeypatch.setattr(
        start.start_flow,
        "get_settings",
        lambda: SimpleNamespace(telegram_home_header_file_id="AgAC-home-header"),
    )

    message = _StartMessage(
        text="/start",
        from_user=SimpleNamespace(id=2, username="bob", first_name="Bob", language_code="de"),
    )
    await start.handle_start(message)

    assert len(message.answers) == 1
    assert message.answers[0].kwargs.get("photo") == "AgAC-home-header"
    assert "Serie:" in (message.answers[0].text or "")
