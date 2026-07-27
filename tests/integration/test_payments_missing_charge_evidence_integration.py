from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.models.payment_inbox import PaymentReconciliationReview
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.session import SessionLocal
from app.economy.purchases.errors import PurchasePrecheckoutValidationError
from app.economy.purchases.service import PurchaseService
from app.economy.purchases.types import PurchaseInitResult
from tests.integration.payments_idempotency_fixtures import UTC, _create_user
from tests.type_helpers import as_any_dict


async def _create_prechecked_premium_purchase(
    *,
    user_id: int,
    idempotency_prefix: str,
    now_utc: datetime,
) -> PurchaseInitResult:
    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="PREMIUM_WEEK",
            idempotency_key=f"{idempotency_prefix}:init",
            now_utc=now_utc,
        )
        await PurchaseService.mark_invoice_sent(session, purchase_id=init.purchase_id)
        await PurchaseService.validate_precheckout(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            total_amount=init.final_stars_amount,
            now_utc=now_utc,
        )
        return init


def _raw_successful_payment(invoice_payload: str, total_amount: int) -> dict[str, object]:
    return {
        "invoice_payload": invoice_payload,
        "currency": "XTR",
        "total_amount": total_amount,
        "telegram_payment_charge_id": "raw-payload-charge-must-not-persist",
        "order_info": {"email": "buyer@example.com", "phone_number": "+49123456789"},
    }


async def _purchase_credit_count(purchase_id: UUID) -> int:
    async with SessionLocal.begin() as session:
        count = await session.scalar(
            select(func.count(LedgerEntry.id)).where(
                LedgerEntry.purchase_id == purchase_id,
                LedgerEntry.entry_type == "PURCHASE_CREDIT",
                LedgerEntry.direction == "CREDIT",
            )
        )
        return int(count or 0)


async def _premium_entitlement_count(*, user_id: int, purchase_id: UUID) -> int:
    async with SessionLocal.begin() as session:
        count = await session.scalar(
            select(func.count(Entitlement.id)).where(
                Entitlement.user_id == user_id,
                Entitlement.source_purchase_id == purchase_id,
                Entitlement.entitlement_type == "PREMIUM",
                Entitlement.status == "ACTIVE",
            )
        )
        return int(count or 0)


@pytest.mark.parametrize(
    ("charge_id", "case_name"),
    [
        (None, "missing"),
        ("", "empty"),
    ],
)
@pytest.mark.asyncio
async def test_missing_or_empty_telegram_payment_charge_id_records_review_without_crediting(
    charge_id: str | None,
    case_name: str,
) -> None:
    now_utc = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    user_id = await _create_user(f"missing-provider-charge-{case_name}")
    init = await _create_prechecked_premium_purchase(
        user_id=user_id,
        idempotency_prefix=f"missing-provider-charge-{case_name}",
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        result = await PurchaseService.mark_successful_payment_paid_uncredited(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id=charge_id,  # type: ignore[arg-type]
            raw_successful_payment=_raw_successful_payment(
                init.invoice_payload,
                init.final_stars_amount,
            ),
            now_utc=now_utc,
        )

    assert result.status == "FAILED_CREDIT_PENDING_REVIEW"

    async with SessionLocal.begin() as session:
        with pytest.raises(PurchasePrecheckoutValidationError):
            await PurchaseService.credit_paid_purchase(
                session,
                purchase_id=init.purchase_id,
                user_id=user_id,
                now_utc=now_utc,
            )

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, init.purchase_id)
        assert purchase is not None
        assert purchase.status == "FAILED_CREDIT_PENDING_REVIEW"
        assert purchase.credited_at is None
        assert purchase.telegram_payment_charge_id == charge_id
        assert purchase.paid_at == now_utc
        assert isinstance(purchase.raw_successful_payment, dict)
        assert purchase.raw_successful_payment["validation_error"] == (
            "missing_telegram_payment_charge_id"
        )
        assert purchase.raw_successful_payment["raw_payload_stored"] is False
        assert "invoice_payload" not in purchase.raw_successful_payment
        assert "telegram_payment_charge_id" not in purchase.raw_successful_payment
        assert "order_info" not in purchase.raw_successful_payment
        assert "raw-payload-charge-must-not-persist" not in repr(purchase.raw_successful_payment)
        assert "buyer@example.com" not in repr(purchase.raw_successful_payment)

        review = await session.scalar(
            select(PaymentReconciliationReview).where(
                PaymentReconciliationReview.purchase_id == init.purchase_id,
                PaymentReconciliationReview.reason == "missing_telegram_payment_charge_id",
            )
        )
        assert review is not None
        assert review.review_type == "SUCCESSFUL_PAYMENT_VALIDATION_FAILED"
        assert review.status == "OPEN"
        assert review.transaction_id_hash is None
        safe_payload = as_any_dict(review.safe_payload)
        assert safe_payload["reason"] == "missing_telegram_payment_charge_id"
        assert safe_payload["raw_payload_stored"] is False
        assert safe_payload["telegram_payment_charge_id_hash"] is None
        assert "invoice_payload" not in safe_payload
        assert "raw-payload-charge-must-not-persist" not in repr(safe_payload)
        assert "buyer@example.com" not in repr(safe_payload)

    assert await _purchase_credit_count(init.purchase_id) == 0
    assert await _premium_entitlement_count(user_id=user_id, purchase_id=init.purchase_id) == 0


@pytest.mark.asyncio
async def test_valid_telegram_payment_charge_id_credits_once_and_duplicate_is_replay() -> None:
    now_utc = datetime(2026, 7, 10, 12, 30, tzinfo=UTC)
    user_id = await _create_user("valid-provider-charge-idempotent")
    init = await _create_prechecked_premium_purchase(
        user_id=user_id,
        idempotency_prefix="valid-provider-charge-idempotent",
        now_utc=now_utc,
    )
    raw_successful_payment = _raw_successful_payment(
        init.invoice_payload,
        init.final_stars_amount,
    )

    async with SessionLocal.begin() as session:
        first = await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_valid_provider_1",
            raw_successful_payment=raw_successful_payment,
            now_utc=now_utc,
        )
        second = await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_valid_provider_1",
            raw_successful_payment=raw_successful_payment,
            now_utc=now_utc,
        )

    assert first.status == "CREDITED"
    assert first.idempotent_replay is False
    assert second.status == "CREDITED"
    assert second.idempotent_replay is True

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, init.purchase_id)
        assert purchase is not None
        assert purchase.status == "CREDITED"
        assert purchase.credited_at is not None
        assert purchase.telegram_payment_charge_id == "tg_charge_valid_provider_1"
        assert isinstance(purchase.raw_successful_payment, dict)
        assert purchase.raw_successful_payment["raw_payload_stored"] is False
        assert "invoice_payload" not in purchase.raw_successful_payment
        assert "telegram_payment_charge_id" not in purchase.raw_successful_payment
        assert "order_info" not in purchase.raw_successful_payment

        review_count = await session.scalar(
            select(func.count(PaymentReconciliationReview.id)).where(
                PaymentReconciliationReview.purchase_id == init.purchase_id,
                PaymentReconciliationReview.reason == "missing_telegram_payment_charge_id",
            )
        )
        assert int(review_count or 0) == 0

    assert await _purchase_credit_count(init.purchase_id) == 1
    assert await _premium_entitlement_count(user_id=user_id, purchase_id=init.purchase_id) == 1


@pytest.mark.asyncio
async def test_credited_replay_repairs_missing_charge_without_duplicate_credit() -> None:
    now_utc = datetime(2026, 7, 10, 13, 0, tzinfo=UTC)
    user_id = await _create_user("credited-replay-missing-charge")
    init = await _create_prechecked_premium_purchase(
        user_id=user_id,
        idempotency_prefix="credited-replay-missing-charge",
        now_utc=now_utc,
    )
    raw_successful_payment = _raw_successful_payment(
        init.invoice_payload,
        init.final_stars_amount,
    )

    async with SessionLocal.begin() as session:
        await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_repair_source",
            raw_successful_payment=raw_successful_payment,
            now_utc=now_utc,
        )

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id_for_update(session, init.purchase_id)
        assert purchase is not None
        purchase.telegram_payment_charge_id = None

    async with SessionLocal.begin() as session:
        replay = await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_repaired",
            raw_successful_payment=raw_successful_payment,
            now_utc=now_utc,
        )

    assert replay.status == "CREDITED"
    assert replay.idempotent_replay is True

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, init.purchase_id)
        assert purchase is not None
        assert purchase.telegram_payment_charge_id == "tg_charge_repaired"
        assert purchase.status == "CREDITED"

    assert await _purchase_credit_count(init.purchase_id) == 1
    assert await _premium_entitlement_count(user_id=user_id, purchase_id=init.purchase_id) == 1
