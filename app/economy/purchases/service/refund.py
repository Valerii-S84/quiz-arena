from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ledger_entries import LedgerEntry
from app.db.repo.energy_repo import EnergyRepo
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.mode_access_repo import ModeAccessRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.streak_repo import StreakRepo
from app.economy.energy.time import berlin_local_date
from app.economy.purchases.errors import (
    PurchaseNotFoundError,
    PurchaseRefundInvariantError,
    PurchaseRefundValidationError,
)
from app.economy.purchases.types import PurchaseRefundResult

REFUNDABLE_PURCHASE_STATUSES = {"CREDITED", "PAID_UNCREDITED"}


def _extract_asset_breakdown(metadata: dict[str, object]) -> dict[str, object]:
    raw_breakdown = metadata.get("asset_breakdown")
    if isinstance(raw_breakdown, dict):
        return raw_breakdown
    return {}


def _extract_non_negative_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    return value if isinstance(value, int) and value > 0 else 0


async def _debit_paid_energy_wallet(
    session: AsyncSession,
    *,
    user_id: int,
    amount: int,
    now_utc: datetime,
) -> None:
    if amount <= 0:
        return

    state = await EnergyRepo.get_by_user_id_for_update(session, user_id)
    if state is None:
        state = await EnergyRepo.create_default_state(
            session,
            user_id=user_id,
            now_utc=now_utc,
            local_date_berlin=berlin_local_date(now_utc),
        )

    debit_amount = min(amount, state.paid_energy)
    if debit_amount <= 0:
        return

    state.paid_energy -= debit_amount
    state.version += 1
    state.updated_at = now_utc
    await session.flush()


async def refund_purchase(
    session: AsyncSession,
    *,
    purchase_id: UUID,
    now_utc: datetime,
) -> PurchaseRefundResult:
    purchase = await PurchasesRepo.get_by_id_for_update(session, purchase_id)
    if purchase is None:
        raise PurchaseNotFoundError

    if purchase.status == "REFUNDED":
        return PurchaseRefundResult(
            purchase_id=purchase.id,
            product_code=purchase.product_code,
            status=purchase.status,
            idempotent_replay=True,
        )

    if purchase.status not in REFUNDABLE_PURCHASE_STATUSES:
        raise PurchaseRefundValidationError

    idempotent_replay = False

    if purchase.status == "CREDITED":
        try:
            credit_entry = await LedgerRepo.get_purchase_credit_for_update(
                session,
                purchase_id=purchase.id,
            )
        except ValueError as exc:
            raise PurchaseRefundInvariantError from exc

        if credit_entry is None:
            raise PurchaseRefundInvariantError

        asset_breakdown = _extract_asset_breakdown(credit_entry.metadata_)
        existing_refund_entry = await LedgerRepo.get_by_idempotency_key(
            session,
            f"refund:{purchase.id}",
        )
        if existing_refund_entry is None:
            paid_energy = _extract_non_negative_int(asset_breakdown, "paid_energy")
            streak_saver_tokens = _extract_non_negative_int(asset_breakdown, "streak_saver_tokens")

            await _debit_paid_energy_wallet(
                session,
                user_id=purchase.user_id,
                amount=paid_energy,
                now_utc=now_utc,
            )
            await StreakRepo.remove_streak_saver_tokens(
                session,
                user_id=purchase.user_id,
                amount=streak_saver_tokens,
                now_utc=now_utc,
            )

            await LedgerRepo.create(
                session,
                entry=LedgerEntry(
                    user_id=purchase.user_id,
                    purchase_id=purchase.id,
                    entry_type="PURCHASE_REFUND",
                    asset=credit_entry.asset,
                    direction="DEBIT",
                    amount=credit_entry.amount,
                    balance_after=None,
                    source="PURCHASE",
                    idempotency_key=f"refund:{purchase.id}",
                    metadata_={
                        "product_code": credit_entry.metadata_.get("product_code"),
                        "asset_breakdown": asset_breakdown,
                        "source_credit_idempotency_key": credit_entry.idempotency_key,
                    },
                    created_at=now_utc,
                ),
            )
        else:
            idempotent_replay = True

        await EntitlementsRepo.revoke_active_or_scheduled_by_purchase(
            session,
            purchase_id=purchase.id,
            now_utc=now_utc,
        )
        await ModeAccessRepo.revoke_active_by_purchase(
            session,
            purchase_id=purchase.id,
            now_utc=now_utc,
        )

    purchase.status = "REFUNDED"
    purchase.refunded_at = purchase.refunded_at or now_utc

    return PurchaseRefundResult(
        purchase_id=purchase.id,
        product_code=purchase.product_code,
        status=purchase.status,
        idempotent_replay=idempotent_replay,
    )
