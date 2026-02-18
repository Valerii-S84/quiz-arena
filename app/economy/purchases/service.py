from __future__ import annotations

from datetime import datetime, timedelta
from math import ceil
from datetime import timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ledger_entries import LedgerEntry
from app.db.models.mode_access import ModeAccess
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase
from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.mode_access_repo import ModeAccessRepo
from app.db.repo.promo_repo import PromoRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.streak_repo import StreakRepo
from app.economy.energy.service import EnergyService
from app.economy.purchases.catalog import MEGA_PACK_MODE_CODES, ProductSpec, get_product
from app.economy.purchases.errors import (
    ProductNotFoundError,
    PurchaseInitValidationError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
)
from app.economy.purchases.types import PurchaseCreditResult, PurchaseInitResult

PROMO_RESERVATION_TTL_MINUTES = 15


class PurchaseService:
    @staticmethod
    def _build_invoice_payload() -> str:
        return f"inv_{uuid4().hex}"

    @staticmethod
    def _calculate_discount_amount(base_price: int, discount_percent: int) -> int:
        discounted = ceil(base_price * (100 - discount_percent) / 100)
        final_price = max(1, discounted)
        return max(0, base_price - final_price)

    @staticmethod
    def _is_promo_scope_applicable(target_scope: str, *, product: ProductSpec) -> bool:
        if target_scope in {product.product_code, "ANY"}:
            return True
        if product.product_type == "MICRO" and target_scope == "MICRO_ANY":
            return True
        if product.product_type == "PREMIUM" and target_scope == "PREMIUM_ANY":
            return True
        return False

    @staticmethod
    def _build_purchase(
        product: ProductSpec,
        *,
        user_id: int,
        idempotency_key: str,
        discount_stars_amount: int,
        applied_promo_code_id: int | None,
        now_utc: datetime,
    ) -> Purchase:
        final_stars_amount = max(1, product.stars_amount - discount_stars_amount)
        return Purchase(
            id=uuid4(),
            user_id=user_id,
            product_code=product.product_code,
            product_type=product.product_type,
            base_stars_amount=product.stars_amount,
            discount_stars_amount=discount_stars_amount,
            stars_amount=final_stars_amount,
            currency="XTR",
            status="CREATED",
            applied_promo_code_id=applied_promo_code_id,
            idempotency_key=idempotency_key,
            invoice_payload=PurchaseService._build_invoice_payload(),
            created_at=now_utc,
        )

    @staticmethod
    async def _validate_and_reserve_discount_redemption(
        session: AsyncSession,
        *,
        redemption_id: UUID,
        user_id: int,
        product: ProductSpec,
        now_utc: datetime,
    ) -> tuple[int, int]:
        redemption = await PromoRepo.get_redemption_by_id_for_update(session, redemption_id)
        if redemption is None or redemption.user_id != user_id:
            raise PurchaseInitValidationError
        if redemption.applied_purchase_id is not None:
            raise PurchaseInitValidationError
        if redemption.status not in {"VALIDATED", "RESERVED"}:
            raise PurchaseInitValidationError

        if redemption.reserved_until is not None and redemption.reserved_until <= now_utc:
            raise PurchaseInitValidationError

        promo_code = await PromoRepo.get_code_by_id_for_update(session, redemption.promo_code_id)
        if promo_code is None:
            raise PurchaseInitValidationError
        if promo_code.promo_type != "PERCENT_DISCOUNT" or promo_code.discount_percent is None:
            raise PurchaseInitValidationError
        if promo_code.status != "ACTIVE":
            raise PurchaseInitValidationError
        if not (promo_code.valid_from <= now_utc < promo_code.valid_until):
            raise PurchaseInitValidationError
        if not PurchaseService._is_promo_scope_applicable(promo_code.target_scope, product=product):
            raise PurchaseInitValidationError
        if promo_code.max_total_uses is not None and promo_code.used_total >= promo_code.max_total_uses:
            raise PurchaseInitValidationError

        discount_stars_amount = PurchaseService._calculate_discount_amount(
            product.stars_amount,
            promo_code.discount_percent,
        )
        redemption.status = "RESERVED"
        redemption.reserved_until = now_utc + timedelta(minutes=PROMO_RESERVATION_TTL_MINUTES)
        redemption.updated_at = now_utc
        return discount_stars_amount, promo_code.id

    @staticmethod
    async def _validate_reserved_discount_for_purchase(
        session: AsyncSession,
        *,
        purchase: Purchase,
        now_utc: datetime,
    ) -> tuple[PromoRedemption, PromoCode]:
        if purchase.applied_promo_code_id is None:
            raise PurchasePrecheckoutValidationError

        redemption = await PromoRepo.get_redemption_by_applied_purchase_id_for_update(session, purchase.id)
        if redemption is None:
            raise PurchasePrecheckoutValidationError
        if redemption.status != "RESERVED":
            raise PurchasePrecheckoutValidationError
        if redemption.reserved_until is None or redemption.reserved_until <= now_utc:
            raise PurchasePrecheckoutValidationError

        promo_code = await PromoRepo.get_code_by_id_for_update(session, purchase.applied_promo_code_id)
        if promo_code is None:
            raise PurchasePrecheckoutValidationError
        if promo_code.promo_type != "PERCENT_DISCOUNT":
            raise PurchasePrecheckoutValidationError
        if promo_code.status != "ACTIVE":
            raise PurchasePrecheckoutValidationError
        if not (promo_code.valid_from <= now_utc < promo_code.valid_until):
            raise PurchasePrecheckoutValidationError

        return redemption, promo_code

    @staticmethod
    async def init_purchase(
        session: AsyncSession,
        *,
        user_id: int,
        product_code: str,
        idempotency_key: str,
        now_utc: datetime,
        promo_redemption_id: UUID | None = None,
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
                base_stars_amount=existing.base_stars_amount,
                discount_stars_amount=existing.discount_stars_amount,
                applied_promo_code_id=existing.applied_promo_code_id,
                idempotent_replay=True,
            )

        discount_stars_amount = 0
        applied_promo_code_id: int | None = None
        if promo_redemption_id is not None:
            discount_stars_amount, applied_promo_code_id = await PurchaseService._validate_and_reserve_discount_redemption(
                session,
                redemption_id=promo_redemption_id,
                user_id=user_id,
                product=product,
                now_utc=now_utc,
            )

        purchase = await PurchasesRepo.create(
            session,
            purchase=PurchaseService._build_purchase(
                product,
                user_id=user_id,
                idempotency_key=idempotency_key,
                discount_stars_amount=discount_stars_amount,
                applied_promo_code_id=applied_promo_code_id,
                now_utc=now_utc,
            ),
            created_at=now_utc,
        )

        if promo_redemption_id is not None:
            redemption = await PromoRepo.get_redemption_by_id_for_update(session, promo_redemption_id)
            if redemption is None:
                raise PurchaseInitValidationError
            redemption.applied_purchase_id = purchase.id
            redemption.updated_at = now_utc

        return PurchaseInitResult(
            purchase_id=purchase.id,
            invoice_payload=purchase.invoice_payload,
            product_code=purchase.product_code,
            final_stars_amount=purchase.stars_amount,
            base_stars_amount=purchase.base_stars_amount,
            discount_stars_amount=purchase.discount_stars_amount,
            applied_promo_code_id=purchase.applied_promo_code_id,
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
            await PurchaseService._validate_reserved_discount_for_purchase(
                session,
                purchase=purchase,
                now_utc=check_time,
            )

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

        previous_status = purchase.status
        purchase.telegram_payment_charge_id = telegram_payment_charge_id
        purchase.raw_successful_payment = raw_successful_payment
        purchase.status = "PAID_UNCREDITED"
        if purchase.paid_at is None or previous_status != "PAID_UNCREDITED":
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

        if purchase.applied_promo_code_id is not None:
            promo_redemption, promo_code = await PurchaseService._validate_reserved_discount_for_purchase(
                session,
                purchase=purchase,
                now_utc=now_utc,
            )
            if promo_redemption.status != "APPLIED":
                if promo_code.max_total_uses is not None and promo_code.used_total >= promo_code.max_total_uses:
                    raise PurchasePrecheckoutValidationError
                promo_redemption.status = "APPLIED"
                promo_redemption.applied_at = now_utc
                promo_redemption.updated_at = now_utc
                promo_code.used_total += 1
                promo_code.updated_at = now_utc

        purchase.status = "CREDITED"
        purchase.credited_at = now_utc

        return PurchaseCreditResult(
            purchase_id=purchase.id,
            product_code=purchase.product_code,
            status=purchase.status,
            idempotent_replay=False,
        )
