from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ledger_entries import LedgerEntry
from app.db.models.mode_access import ModeAccess
from app.db.models.purchases import Purchase
from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.mode_access_repo import ModeAccessRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.streak_repo import StreakRepo
from app.economy.energy.service import EnergyService
from app.economy.purchases.catalog import MEGA_PACK_MODE_CODES, ProductSpec, get_product
from app.economy.purchases.errors import (
    ProductNotFoundError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
)
from app.economy.purchases.types import PurchaseCreditResult, PurchaseInitResult


class PurchaseService:
    @staticmethod
    def _build_invoice_payload() -> str:
        return f"inv_{uuid4().hex}"

    @staticmethod
    def _build_purchase(product: ProductSpec, *, user_id: int, idempotency_key: str, now_utc: datetime) -> Purchase:
        return Purchase(
            id=uuid4(),
            user_id=user_id,
            product_code=product.product_code,
            product_type=product.product_type,
            base_stars_amount=product.stars_amount,
            discount_stars_amount=0,
            stars_amount=product.stars_amount,
            currency="XTR",
            status="CREATED",
            idempotency_key=idempotency_key,
            invoice_payload=PurchaseService._build_invoice_payload(),
            created_at=now_utc,
        )

    @staticmethod
    async def init_purchase(
        session: AsyncSession,
        *,
        user_id: int,
        product_code: str,
        idempotency_key: str,
        now_utc: datetime,
    ) -> PurchaseInitResult:
        product = get_product(product_code)
        if product is None:
            raise ProductNotFoundError

        existing = await PurchasesRepo.get_by_idempotency_key(session, idempotency_key)
        if existing is not None:
            return PurchaseInitResult(
                purchase_id=existing.id,
                invoice_payload=existing.invoice_payload,
                product_code=existing.product_code,
                final_stars_amount=existing.stars_amount,
                idempotent_replay=True,
            )

        purchase = await PurchasesRepo.create(
            session,
            purchase=PurchaseService._build_purchase(
                product,
                user_id=user_id,
                idempotency_key=idempotency_key,
                now_utc=now_utc,
            ),
            created_at=now_utc,
        )

        return PurchaseInitResult(
            purchase_id=purchase.id,
            invoice_payload=purchase.invoice_payload,
            product_code=purchase.product_code,
            final_stars_amount=purchase.stars_amount,
            idempotent_replay=False,
        )

    @staticmethod
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

    @staticmethod
    async def validate_precheckout(
        session: AsyncSession,
        *,
        user_id: int,
        invoice_payload: str,
        total_amount: int,
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

        purchase.status = "PRECHECKOUT_OK"

    @staticmethod
    async def apply_successful_payment(
        session: AsyncSession,
        *,
        user_id: int,
        invoice_payload: str,
        telegram_payment_charge_id: str,
        raw_successful_payment: dict[str, object],
        now_utc: datetime,
    ) -> PurchaseCreditResult:
        purchase = await PurchasesRepo.get_by_invoice_payload_for_update(session, invoice_payload)
        if purchase is None or purchase.user_id != user_id:
            raise PurchaseNotFoundError

        if purchase.status == "CREDITED":
            return PurchaseCreditResult(
                purchase_id=purchase.id,
                product_code=purchase.product_code,
                status=purchase.status,
                idempotent_replay=True,
            )

        if purchase.status not in {"PRECHECKOUT_OK", "INVOICE_SENT", "CREATED", "PAID_UNCREDITED"}:
            raise PurchasePrecheckoutValidationError

        purchase.telegram_payment_charge_id = telegram_payment_charge_id
        purchase.raw_successful_payment = raw_successful_payment
        purchase.status = "PAID_UNCREDITED"
        purchase.paid_at = now_utc

        product = get_product(purchase.product_code)
        if product is None:
            raise ProductNotFoundError

        if product.energy_credit > 0:
            await EnergyService.credit_paid_energy(
                session,
                user_id=user_id,
                amount=product.energy_credit,
                idempotency_key=f"credit:energy:{purchase.id}",
                now_utc=now_utc,
            )

        if product.grants_streak_saver:
            streak_state = await StreakRepo.add_streak_saver_token(
                session,
                user_id=user_id,
                now_utc=now_utc,
            )
            await LedgerRepo.create(
                session,
                entry=LedgerEntry(
                    user_id=user_id,
                    purchase_id=purchase.id,
                    entry_type="PURCHASE_CREDIT",
                    asset="STREAK_SAVER",
                    direction="CREDIT",
                    amount=1,
                    balance_after=streak_state.streak_saver_tokens,
                    source="PURCHASE",
                    idempotency_key=f"credit:streak_saver:{purchase.id}",
                    metadata_={},
                    created_at=now_utc,
                ),
            )

        if product.grants_mega_mode_access:
            for mode_code in MEGA_PACK_MODE_CODES:
                latest_end = await ModeAccessRepo.get_latest_active_end(
                    session,
                    user_id=user_id,
                    mode_code=mode_code,
                    source="MEGA_PACK",
                    now_utc=now_utc,
                )
                starts_at = latest_end if latest_end is not None and latest_end > now_utc else now_utc
                ends_at = starts_at + timedelta(hours=24)

                await ModeAccessRepo.create(
                    session,
                    mode_access=ModeAccess(
                        user_id=user_id,
                        mode_code=mode_code,
                        source="MEGA_PACK",
                        starts_at=starts_at,
                        ends_at=ends_at,
                        status="ACTIVE",
                        source_purchase_id=purchase.id,
                        idempotency_key=f"mode_access:{purchase.id}:{mode_code}",
                        created_at=now_utc,
                    ),
                )

        purchase.status = "CREDITED"
        purchase.credited_at = now_utc

        return PurchaseCreditResult(
            purchase_id=purchase.id,
            product_code=purchase.product_code,
            status=purchase.status,
            idempotent_replay=False,
        )
