from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.purchases_repo import PurchasesRepo
from app.economy.purchases.errors import (
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
)

from .events import _emit_purchase_event
from .validation import _validate_reserved_discount_for_purchase


async def mark_invoice_sent(
    session: AsyncSession,
    *,
    purchase_id: UUID,
) -> None:
    purchase = await PurchasesRepo.get_by_id_for_update(session, purchase_id)
    if purchase is None:
        raise PurchaseNotFoundError
    if purchase.status == "CREATED":
        purchase.status = "INVOICE_SENT"
        await _emit_purchase_event(
            session,
            event_type="purchase_invoice_sent",
            purchase=purchase,
            happened_at=datetime.now(timezone.utc),
        )


async def validate_precheckout(
    session: AsyncSession,
    *,
    user_id: int,
    invoice_payload: str,
    total_amount: int,
    now_utc: datetime | None = None,
) -> None:
    purchase = await PurchasesRepo.get_by_invoice_payload_for_update(session, invoice_payload)
    if purchase is None:
        raise PurchasePrecheckoutValidationError
    if purchase.user_id != user_id:
        raise PurchasePrecheckoutValidationError
    if purchase.stars_amount != total_amount:
        raise PurchasePrecheckoutValidationError
    if purchase.status not in {"CREATED", "INVOICE_SENT", "PRECHECKOUT_OK"}:
        raise PurchasePrecheckoutValidationError

    check_time = now_utc or datetime.now(timezone.utc)
    if purchase.applied_promo_code_id is not None:
        await _validate_reserved_discount_for_purchase(
            session,
            purchase=purchase,
            now_utc=check_time,
        )

    if purchase.status != "PRECHECKOUT_OK":
        purchase.status = "PRECHECKOUT_OK"
        await _emit_purchase_event(
            session,
            event_type="purchase_precheckout_ok",
            purchase=purchase,
            happened_at=check_time,
        )
