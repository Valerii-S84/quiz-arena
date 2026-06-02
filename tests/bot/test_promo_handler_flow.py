from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from aiogram.dispatcher.event.bases import SkipHandler

from app.bot.handlers import promo, promo_input, promo_redeem
from app.bot.texts.de import TEXTS_DE
from app.economy.promo.errors import PromoInvalidError
from app.economy.promo.types import PromoRedeemResult
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


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


class _State:
    def __init__(self) -> None:
        self.set_states: list[object] = []
        self.clear_calls = 0
        self.data: dict[str, object] = {}

    async def set_state(self, state: object) -> None:
        self.set_states.append(state)

    async def update_data(self, data: dict[str, object]) -> dict[str, object]:
        self.data.update(data)
        return dict(self.data)

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)

    async def clear(self) -> None:
        self.clear_calls += 1
        self.data.clear()


@pytest.mark.asyncio
async def test_redeem_promo_from_text_handles_missing_user(monkeypatch) -> None:
    message = _PromoMessage(text="/promo CHIK", from_user=None)

    await promo._redeem_promo_from_text(message)  # type: ignore[arg-type]

    assert message.answers[0].text == TEXTS_DE["msg.system.error"]


@pytest.mark.asyncio
async def test_redeem_promo_from_text_prompts_when_code_missing() -> None:
    message = _PromoMessage(text="/promo", from_user=SimpleNamespace(id=1))
    state = _State()

    await promo._redeem_promo_from_text(message, state=state)  # type: ignore[arg-type]

    assert message.answers[0].text == TEXTS_DE["msg.promo.input.hint"]
    assert message.answers[0].kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        "promo:cancel"
    )
    assert state.set_states == [promo.PromoCode.waiting_for_code]


@pytest.mark.asyncio
async def test_prompt_for_promo_input_does_not_use_force_reply() -> None:
    message = _PromoMessage(text="/promo", from_user=SimpleNamespace(id=1))
    state = _State()

    await promo._prompt_for_promo_input(message, state)  # type: ignore[arg-type]

    assert message.answers[0].text == TEXTS_DE["msg.promo.input.hint"]
    assert message.answers[0].kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        "promo:cancel"
    )
    assert state.set_states == [promo.PromoCode.waiting_for_code]
    assert isinstance(state.data[promo_input.PROMO_WAIT_STARTED_AT_KEY], int)


@pytest.mark.asyncio
async def test_handle_promo_waiting_command_passthrough_clears_and_skips() -> None:
    message = _PromoMessage(text="/referral", from_user=SimpleNamespace(id=1))
    state = _State()
    state.data[promo_input.PROMO_WAIT_STARTED_AT_KEY] = 9_999_999_999

    with pytest.raises(SkipHandler):
        await promo.handle_promo_waiting_command_passthrough(  # type: ignore[arg-type]
            message,
            state=state,
        )

    assert state.clear_calls == 1
    assert state.data == {}
    assert message.answers == []


@pytest.mark.asyncio
async def test_handle_promo_code_input_ignores_expired_waiting_state(monkeypatch) -> None:
    message = _PromoMessage(text="SALE15", from_user=SimpleNamespace(id=1))
    state = _State()
    state.data[promo_input.PROMO_WAIT_STARTED_AT_KEY] = 0
    called = False

    async def _fake_redeem(*args, **kwargs) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(promo, "_redeem_promo_from_text", _fake_redeem)

    await promo.handle_promo_code_input(message, state=state)  # type: ignore[arg-type]

    assert called is False
    assert state.clear_calls == 1
    assert message.answers == []


@pytest.mark.asyncio
async def test_handle_promo_code_input_accepts_unexpired_waiting_state(monkeypatch) -> None:
    message = _PromoMessage(text="SALE15", from_user=SimpleNamespace(id=1))
    state = _State()
    state.data[promo_input.PROMO_WAIT_STARTED_AT_KEY] = 9_999_999_999
    captured: dict[str, object] = {}

    async def _fake_redeem(*args, **kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(promo, "_redeem_promo_from_text", _fake_redeem)

    await promo.handle_promo_code_input(message, state=state)  # type: ignore[arg-type]

    assert captured["state"] is state
    assert captured["allow_plain_text"] is True
    assert captured["from_waiting_state"] is True
    assert state.clear_calls == 0


@pytest.mark.asyncio
async def test_handle_promo_open_prompts_for_accessible_callback_message(monkeypatch) -> None:
    monkeypatch.setattr(promo, "Message", DummyMessage)
    state = _State()
    callback = DummyCallback(
        data="promo:open",
        from_user=SimpleNamespace(id=1),
        message=DummyMessage(),
    )

    await promo.handle_promo_open(callback, state=state)  # type: ignore[arg-type]

    assert callback.message.answers[0].text == TEXTS_DE["msg.promo.input.hint"]
    assert callback.message.answers[0].kwargs["reply_markup"].inline_keyboard[0][
        0
    ].callback_data == ("promo:cancel")
    assert state.set_states == [promo.PromoCode.waiting_for_code]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_promo_open_ignores_inaccessible_callback_message() -> None:
    state = _State()
    callback = DummyCallback(
        data="promo:open",
        from_user=SimpleNamespace(id=1),
        message=DummyMessage(),
    )
    callback.message = cast(Any, object())

    await promo.handle_promo_open(callback, state=state)  # type: ignore[arg-type]

    assert state.set_states == []
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_promo_cancel_clears_state_and_returns_to_shop(monkeypatch) -> None:
    monkeypatch.setattr(promo, "Message", DummyMessage)
    state = _State()
    callback = DummyCallback(
        data="promo:cancel",
        from_user=SimpleNamespace(id=1),
        message=DummyMessage(),
    )

    await promo.handle_promo_cancel(callback, state=state)  # type: ignore[arg-type]

    assert state.clear_calls == 1
    assert callback.message.answers[0].text == TEXTS_DE["msg.promo.cancelled"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_redeem_promo_from_text_handles_invalid_code(monkeypatch) -> None:
    monkeypatch.setattr(promo_redeem, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=55)

    async def _fake_redeem(*args, **kwargs):
        raise PromoInvalidError()

    monkeypatch.setattr(
        promo_redeem.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot
    )
    monkeypatch.setattr(promo_redeem.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(text="/promo BADCODE", from_user=SimpleNamespace(id=1))
    await promo._redeem_promo_from_text(message)

    assert message.answers[-1].text == TEXTS_DE["msg.promo.error.invalid"]


@pytest.mark.asyncio
async def test_redeem_promo_from_text_handles_premium_grant(monkeypatch) -> None:
    monkeypatch.setattr(promo_redeem, "SessionLocal", DummySessionLocal())

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

    monkeypatch.setattr(
        promo_redeem.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot
    )
    monkeypatch.setattr(promo_redeem.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(text="/promo BONUS", from_user=SimpleNamespace(id=2))
    await promo._redeem_promo_from_text(message)

    assert message.answers[0].text == TEXTS_DE["msg.promo.success.grant"]
    assert "7 Tage Premium" in (message.answers[1].text or "")


@pytest.mark.asyncio
async def test_redeem_promo_from_text_handles_discount_success(monkeypatch) -> None:
    monkeypatch.setattr(promo_redeem, "SessionLocal", DummySessionLocal())

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

    monkeypatch.setattr(
        promo_redeem.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot
    )
    monkeypatch.setattr(promo_redeem.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(text="/promo SALE25", from_user=SimpleNamespace(id=3))
    await promo._redeem_promo_from_text(message)

    assert message.answers[0].text == TEXTS_DE["msg.promo.success.discount"]
    assert "25% Rabatt" in (message.answers[1].text or "")


@pytest.mark.asyncio
async def test_redeem_promo_from_text_marks_command_source(monkeypatch) -> None:
    monkeypatch.setattr(promo_redeem, "SessionLocal", DummySessionLocal())
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

    monkeypatch.setattr(
        promo_redeem.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot
    )
    monkeypatch.setattr(promo_redeem.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(text="/promo SALE15", from_user=SimpleNamespace(id=5))
    await promo._redeem_promo_from_text(message)

    assert captured["source"] == "COMMAND"


@pytest.mark.asyncio
async def test_redeem_promo_from_waiting_state_marks_button_source_and_clears_state(
    monkeypatch,
) -> None:
    monkeypatch.setattr(promo_redeem, "SessionLocal", DummySessionLocal())
    captured: dict[str, object] = {}
    state = _State()

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

    monkeypatch.setattr(
        promo_redeem.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot
    )
    monkeypatch.setattr(promo_redeem.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(
        text="SALE15",
        from_user=SimpleNamespace(id=6),
    )
    await promo._redeem_promo_from_text(
        message,
        state=state,  # type: ignore[arg-type]
        allow_plain_text=True,
        from_waiting_state=True,
    )

    assert captured["source"] == "BUTTON"
    assert state.clear_calls == 1


@pytest.mark.asyncio
async def test_redeem_promo_from_text_accepts_discount_targets_that_are_now_saleable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(promo_redeem, "SessionLocal", DummySessionLocal())

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

    monkeypatch.setattr(
        promo_redeem.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot
    )
    monkeypatch.setattr(promo_redeem.PromoService, "redeem", _fake_redeem)

    message = _PromoMessage(text="/promo YEAR25", from_user=SimpleNamespace(id=7))
    await promo._redeem_promo_from_text(message)

    assert message.answers[0].text == TEXTS_DE["msg.promo.success.discount"]
    callbacks = [
        button.callback_data
        for row in message.answers[0].kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert any(callback.startswith("buy:PREMIUM_YEAR:promo:") for callback in callbacks)
