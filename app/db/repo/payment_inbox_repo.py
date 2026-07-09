from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.payment_inbox import (
    PaymentEvent,
    PaymentReconciliationReview,
    TelegramUpdateInbox,
)


class TelegramUpdateInboxRepo:
    @staticmethod
    async def create_once(
        session: AsyncSession,
        *,
        update_id: int,
        update_kind: str,
        idempotency_key: str,
        payload_hash: str,
        sanitized_evidence: dict[str, object],
    ) -> tuple[TelegramUpdateInbox, bool]:
        stmt = (
            insert(TelegramUpdateInbox)
            .values(
                update_id=update_id,
                update_kind=update_kind,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                sanitized_evidence=sanitized_evidence,
            )
            .on_conflict_do_nothing(index_elements=[TelegramUpdateInbox.update_id])
            .returning(TelegramUpdateInbox)
        )
        result = await session.execute(stmt)
        created = result.scalar_one_or_none()
        if created is not None:
            return created, True
        existing = await TelegramUpdateInboxRepo.get_by_update_id(session, update_id=update_id)
        if existing is None:
            raise RuntimeError("telegram_update_inbox idempotent insert returned no row")
        return existing, False

    @staticmethod
    async def get_by_update_id(
        session: AsyncSession,
        *,
        update_id: int,
    ) -> TelegramUpdateInbox | None:
        stmt = select(TelegramUpdateInbox).where(TelegramUpdateInbox.update_id == update_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


class PaymentEventsRepo:
    @staticmethod
    async def create_once(
        session: AsyncSession,
        *,
        provider: str,
        event_type: str,
        idempotency_key: str,
        source_inbox_update_id: int | None,
        invoice_payload: str | None,
        provider_charge_id_hash: str | None,
        provider_payment_charge_id_hash: str | None,
        currency: str | None,
        total_amount: int | None,
        telegram_user_id: int | None,
        safe_payload: dict[str, object],
        purchase_id: UUID | None = None,
        user_id: int | None = None,
    ) -> tuple[PaymentEvent, bool]:
        stmt = (
            insert(PaymentEvent)
            .values(
                provider=provider,
                event_type=event_type,
                idempotency_key=idempotency_key,
                source_inbox_update_id=source_inbox_update_id,
                purchase_id=purchase_id,
                user_id=user_id,
                telegram_user_id=telegram_user_id,
                invoice_payload=invoice_payload,
                provider_charge_id_hash=provider_charge_id_hash,
                provider_payment_charge_id_hash=provider_payment_charge_id_hash,
                currency=currency,
                total_amount=total_amount,
                safe_payload=safe_payload,
            )
            .on_conflict_do_nothing(index_elements=[PaymentEvent.idempotency_key])
            .returning(PaymentEvent)
        )
        result = await session.execute(stmt)
        created = result.scalar_one_or_none()
        if created is not None:
            return created, True
        existing = await PaymentEventsRepo.get_by_idempotency_key(
            session,
            idempotency_key=idempotency_key,
        )
        if existing is None:
            raise RuntimeError("payment_events idempotent insert returned no row")
        return existing, False

    @staticmethod
    async def get_by_idempotency_key(
        session: AsyncSession,
        *,
        idempotency_key: str,
    ) -> PaymentEvent | None:
        stmt = select(PaymentEvent).where(PaymentEvent.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


class PaymentReconciliationReviewsRepo:
    @staticmethod
    async def create_once(
        session: AsyncSession,
        *,
        unique_key: str,
        review_type: str,
        severity: str,
        reason: str,
        safe_payload: dict[str, object],
        payment_event_id: int | None = None,
        purchase_id: UUID | None = None,
        transaction_id_hash: str | None = None,
    ) -> tuple[PaymentReconciliationReview, bool]:
        stmt = (
            insert(PaymentReconciliationReview)
            .values(
                unique_key=unique_key,
                review_type=review_type,
                severity=severity,
                reason=reason,
                payment_event_id=payment_event_id,
                purchase_id=purchase_id,
                transaction_id_hash=transaction_id_hash,
                safe_payload=safe_payload,
            )
            .on_conflict_do_nothing(index_elements=[PaymentReconciliationReview.unique_key])
            .returning(PaymentReconciliationReview)
        )
        result = await session.execute(stmt)
        created = result.scalar_one_or_none()
        if created is not None:
            return created, True
        existing = await PaymentReconciliationReviewsRepo.get_by_unique_key(
            session,
            unique_key=unique_key,
        )
        if existing is None:
            raise RuntimeError("payment_reconciliation_reviews idempotent insert returned no row")
        return existing, False

    @staticmethod
    async def get_by_unique_key(
        session: AsyncSession,
        *,
        unique_key: str,
    ) -> PaymentReconciliationReview | None:
        stmt = select(PaymentReconciliationReview).where(
            PaymentReconciliationReview.unique_key == unique_key
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
