from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import promo
from app.bot.texts.de import TEXTS_DE
from app.economy.promo.errors import PromoInvalidError
from app.economy.promo.types import PromoRedeemResult
from tests.bot.helpers import DummyMessage, DummySessionLocal


class _PromoMessage(DummyMessage):
    def __init__(
        self,
        *,
        text: str,
        from_user: SimpleNamespace | None = None,
        message_id: int = 10,
        reply_to_promo_prompt: bool = False,
    ) -> None:
        super().__init__()
        self.text = text
        self.from_user = from_user
        self.message_id = message_id
        self.reply_to_message = None
        if reply_to_promo_prompt:
            self.reply_to_message = SimpleNamespace(
                from_user=SimpleNamespace(is_bot=True),
                text=TEXTS_DE["msg.promo.reply_prefix"],
            )


@pytest.mark.asyncio
async def test_redeem_promo_from_text_handles_missing_user(monkeypatch) -> None:
    message = _PromoMessage(text="/promo CHIK", from_user=None)

    await promo._redeem_promo_from_text(message)  # type: ignore[arg-type]

    assert message.answers[0].text == TEXTS_DE["msg.system.error"]


@pytest.mark.asyncio
async def test_redeem_promo_from_text_prompts_when_code_missing() -> None:
    message = _PromoMessage(text="/promo", from_user=SimpleNamespace(id=1))

    await promo._redeem_promo_from_text(message)

    assert message.answers[0].text == TEXTS_DE["msg.promo.input.hint"]
    assert "reply_markup" not in message.answers[0].kwargs


@pytest.mark.asyncio
async def test_prompt_for_promo_input_does_not_use_force_reply() -> None:
    message = _PromoMessage(text="/promo", from_user=SimpleNamespace(id=1))

    await promo._prompt_for_promo_input(message)

    assert message.answers[0].text == TEXTS_DE["msg.promo.input.hint"]
    assert "reply_markup" not in message.answers[0].kwargs


@pytest.mark.asyncio
async def test_redeem_promo_from_text_handles_invalid_code(monkeypatch) -> None:
    monkeypatch.setattr(promo, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=55)

    async def _fake_redeem(*args, **kwargs):
        raise PromoInvalidError()

    monkeypatch.setattr(promo.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(promo.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(text="/promo BADCODE", from_user=SimpleNamespace(id=1))
    await promo._redeem_promo_from_text(message)

    assert message.answers[-1].text == TEXTS_DE["msg.promo.error.invalid"]


@pytest.mark.asyncio
async def test_redeem_promo_from_text_handles_premium_grant(monkeypatch) -> None:
    monkeypatch.setattr(promo, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=77)

    async def _fake_redeem(*args, **kwargs):
        return PromoRedeemResult(
            redemption_id=UUID("11111111-1111-1111-1111-111111111111"),
            result_type="PREMIUM_GRANT",
            idempotent_replay=False,
            premium_days=7,
            premium_ends_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(promo.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(promo.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(text="/promo BONUS", from_user=SimpleNamespace(id=2))
    await promo._redeem_promo_from_text(message)

    assert message.answers[0].text == TEXTS_DE["msg.promo.success.grant"]
    assert "7 Tage Premium" in (message.answers[1].text or "")


@pytest.mark.asyncio
async def test_redeem_promo_from_text_handles_discount_success(monkeypatch) -> None:
    monkeypatch.setattr(promo, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=99)

    async def _fake_redeem(*args, **kwargs):
        return PromoRedeemResult(
            redemption_id=UUID("22222222-2222-2222-2222-222222222222"),
            result_type="PERCENT_DISCOUNT",
            idempotent_replay=False,
            discount_percent=25,
            target_scope="PREMIUM_MONTH",
            reserved_until=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(promo.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(promo.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(text="/promo SALE25", from_user=SimpleNamespace(id=3))
    await promo._redeem_promo_from_text(message)

    assert message.answers[0].text == TEXTS_DE["msg.promo.success.discount"]
    assert "25% Rabatt" in (message.answers[1].text or "")


@pytest.mark.asyncio
async def test_handle_promo_plain_text_redeems_code(monkeypatch) -> None:
    monkeypatch.setattr(promo, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=101)

    async def _fake_redeem(*args, **kwargs):
        return PromoRedeemResult(
            redemption_id=UUID("33333333-3333-3333-3333-333333333333"),
            result_type="PERCENT_DISCOUNT",
            idempotent_replay=False,
            discount_percent=30,
            target_scope="ANY",
            reserved_until=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(promo.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(promo.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(text="CHIK3", from_user=SimpleNamespace(id=3))
    await promo.handle_promo_plain_text(message)  # type: ignore[arg-type]

    assert message.answers[0].text == TEXTS_DE["msg.promo.success.discount"]
    assert "30% Rabatt" in (message.answers[1].text or "")


@pytest.mark.asyncio
async def test_redeem_promo_from_text_marks_command_source(monkeypatch) -> None:
    monkeypatch.setattr(promo, "SessionLocal", DummySessionLocal())
    captured: dict[str, object] = {}

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=15)

    async def _fake_redeem(*args, **kwargs):
        captured.update(kwargs)
        return PromoRedeemResult(
            redemption_id=UUID("44444444-4444-4444-4444-444444444444"),
            result_type="PERCENT_DISCOUNT",
            idempotent_replay=False,
            discount_percent=15,
            target_scope="ENERGY_10",
            reserved_until=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(promo.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(promo.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(text="/promo SALE15", from_user=SimpleNamespace(id=5))
    await promo._redeem_promo_from_text(message)

    assert captured["source"] == "COMMAND"


@pytest.mark.asyncio
async def test_redeem_promo_from_reply_marks_button_source(monkeypatch) -> None:
    monkeypatch.setattr(promo, "SessionLocal", DummySessionLocal())
    captured: dict[str, object] = {}

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=16)

    async def _fake_redeem(*args, **kwargs):
        captured.update(kwargs)
        return PromoRedeemResult(
            redemption_id=UUID("55555555-5555-5555-5555-555555555555"),
            result_type="PERCENT_DISCOUNT",
            idempotent_replay=False,
            discount_percent=15,
            target_scope="ENERGY_10",
            reserved_until=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(promo.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(promo.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(
        text="SALE15",
        from_user=SimpleNamespace(id=6),
        reply_to_promo_prompt=True,
    )
    await promo._redeem_promo_from_text(message)

    assert captured["source"] == "BUTTON"


@pytest.mark.asyncio
async def test_redeem_promo_from_text_reports_unavailable_discount_targets(monkeypatch) -> None:
    monkeypatch.setattr(promo, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=77)

    async def _fake_redeem(*args, **kwargs):
        return PromoRedeemResult(
            redemption_id=UUID("66666666-6666-6666-6666-666666666666"),
            result_type="PERCENT_DISCOUNT",
            idempotent_replay=False,
            discount_percent=25,
            target_scope="PREMIUM_YEAR",
            reserved_until=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(promo.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(promo.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(text="/promo YEAR25", from_user=SimpleNamespace(id=7))
    await promo._redeem_promo_from_text(message)

    assert message.answers[0].text == TEXTS_DE["msg.promo.discount.unavailable"]
