from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from aiogram.types import SuccessfulPayment, User

from app.bot.handlers import payments_runtime
from app.economy.purchases.errors import PurchasePrecheckoutValidationError
from app.economy.purchases.types import PurchaseCreditResult

UTC = timezone.utc
PURCHASE_ID = UUID("123e4567-e89b-12d3-a456-426614174321")


class _SuccessfulPayment:
    invoice_payload = "inv-1"
    telegram_payment_charge_id = "charge-1"

    def model_dump(self, exclude_none: bool = True) -> dict[str, object]:
        assert exclude_none is True
        return {
            "invoice_payload": self.invoice_payload,
            "currency": "XTR",
            "total_amount": 5,
            "telegram_payment_charge_id": "raw-charge-in-payload",
        }


class _SessionContext:
    def __init__(self, owner: "_SessionLocal", index: int) -> None:
        self._owner = owner
        self._index = index
        self.session = SimpleNamespace(name=f"session-{index}")

    async def __aenter__(self):
        self._owner.events.append(f"begin:{self._index}")
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        status = "rollback" if exc_type is not None else "commit"
        self._owner.events.append(f"{status}:{self._index}")
        return False


class _SessionLocal:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self._next_index = 0

    def begin(self) -> _SessionContext:
        self._next_index += 1
        return _SessionContext(self, self._next_index)


def _credit_result(status: str, *, replay: bool = False) -> PurchaseCreditResult:
    return PurchaseCreditResult(
        purchase_id=PURCHASE_ID,
        product_code="ENERGY_10",
        status=status,
        idempotent_replay=replay,
    )


def _telegram_user() -> User:
    return cast(User, SimpleNamespace(id=1))


def _payment() -> SuccessfulPayment:
    return cast(SuccessfulPayment, _SuccessfulPayment())


def _wire_runtime(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    monkeypatch.setattr(payments_runtime, "SessionLocal", _SessionLocal(events))

    async def _fake_home_snapshot(_session, *, telegram_user):
        events.append("home")
        return SimpleNamespace(user_id=77)

    async def _fake_offer_conversion(*_args, **_kwargs) -> None:
        events.append("offer")

    monkeypatch.setattr(
        payments_runtime.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_home_snapshot,
    )
    monkeypatch.setattr(payments_runtime, "mark_payment_offer_conversion", _fake_offer_conversion)


@pytest.mark.asyncio
async def test_successful_payment_commits_paid_checkpoint_before_credit(monkeypatch) -> None:
    events: list[str] = []
    _wire_runtime(monkeypatch, events)

    async def _mark_paid(*_args, **_kwargs):
        events.append("mark_paid")
        return _credit_result("PAID_UNCREDITED")

    async def _credit(*_args, **_kwargs):
        assert "commit:1" in events
        events.append("credit")
        return _credit_result("CREDITED")

    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "mark_successful_payment_paid_uncredited",
        _mark_paid,
    )
    monkeypatch.setattr(payments_runtime.PurchaseService, "credit_paid_purchase", _credit)

    result = await payments_runtime.apply_successful_payment(
        telegram_user=_telegram_user(),
        payment=_payment(),
        now_utc=datetime.now(UTC),
    )

    assert result.status == "CREDITED"
    assert events == [
        "begin:1",
        "home",
        "mark_paid",
        "commit:1",
        "begin:2",
        "credit",
        "offer",
        "commit:2",
    ]


@pytest.mark.asyncio
async def test_credit_failure_after_checkpoint_leaves_first_transaction_committed(
    monkeypatch,
) -> None:
    events: list[str] = []
    _wire_runtime(monkeypatch, events)

    async def _mark_paid(*_args, **_kwargs):
        events.append("mark_paid")
        return _credit_result("PAID_UNCREDITED")

    async def _fail_credit(*_args, **_kwargs):
        assert "commit:1" in events
        events.append("credit_failed")
        raise RuntimeError("credit down")

    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "mark_successful_payment_paid_uncredited",
        _mark_paid,
    )
    monkeypatch.setattr(payments_runtime.PurchaseService, "credit_paid_purchase", _fail_credit)

    with pytest.raises(RuntimeError):
        await payments_runtime.apply_successful_payment(
            telegram_user=_telegram_user(),
            payment=_payment(),
            now_utc=datetime.now(UTC),
        )

    assert events == [
        "begin:1",
        "home",
        "mark_paid",
        "commit:1",
        "begin:2",
        "credit_failed",
        "rollback:2",
    ]


@pytest.mark.asyncio
async def test_validation_review_result_commits_before_handler_failure(monkeypatch) -> None:
    events: list[str] = []
    _wire_runtime(monkeypatch, events)

    async def _mark_failed(*_args, **_kwargs):
        events.append("mark_review")
        return _credit_result("FAILED_CREDIT_PENDING_REVIEW")

    async def _credit(*_args, **_kwargs):
        raise AssertionError("validation failure must not enter credit phase")

    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "mark_successful_payment_paid_uncredited",
        _mark_failed,
    )
    monkeypatch.setattr(payments_runtime.PurchaseService, "credit_paid_purchase", _credit)

    with pytest.raises(PurchasePrecheckoutValidationError):
        await payments_runtime.apply_successful_payment(
            telegram_user=_telegram_user(),
            payment=_payment(),
            now_utc=datetime.now(UTC),
        )

    assert events == ["begin:1", "home", "mark_review", "commit:1"]
