from __future__ import annotations

from dataclasses import dataclass

from app.db.repo.telegram_delivery_attempts_repo import TelegramDeliveryAttemptsRepo
from app.db.session import SessionLocal
from app.services.telegram_delivery_outcomes import (
    TelegramDeliveryExceptionOutcome,
    classify_telegram_delivery_exception,
)
from app.workers.tasks.tournaments_message_delivery_terminal import (
    PrivateTournamentStandingsFence,
    persist_private_tournament_sent_message,
)
from app.workers.tasks.tournaments_messaging_delivery_targets import (
    SKIP_CODE_NO_CHAT,
    PrivateTournamentDeliveryTarget,
)

_PENDING_REPLAY_CLAIM_TTL_SECONDS = 300
_RETRY_NEEDED_FAILURE_CODE = "TELEGRAM_RETRY_NEEDED"


@dataclass(frozen=True, slots=True)
class PrivateTournamentDeliveryPreparation:
    should_send: bool
    status: str
    created: bool


async def prepare_private_tournament_delivery(
    target: PrivateTournamentDeliveryTarget,
) -> PrivateTournamentDeliveryPreparation:
    async with SessionLocal.begin() as session:
        row, created = await TelegramDeliveryAttemptsRepo.create_once(
            session,
            attempt=target.attempt,
        )
        current_status = str(getattr(row, "status", "PENDING"))
        if target.chat_id is None:
            skipped = await TelegramDeliveryAttemptsRepo.mark_skipped(
                session,
                idempotency_key=target.idempotency_key,
                failure_code=SKIP_CODE_NO_CHAT,
                failure_reason="target has no chat id",
            )
            if not skipped:
                raise RuntimeError("private tournament missing-chat delivery lease was lost")
            return PrivateTournamentDeliveryPreparation(
                should_send=False,
                status="SKIPPED",
                created=created,
            )
        if current_status in {"SENT", "SKIPPED", "FAILED"}:
            return PrivateTournamentDeliveryPreparation(
                should_send=False,
                status=current_status,
                created=created,
            )
        if not created and current_status == "PENDING":
            retry_deferred = getattr(row, "failure_code", None) == _RETRY_NEEDED_FAILURE_CODE
            if target.pending_replay_safe or retry_deferred:
                claimed = await TelegramDeliveryAttemptsRepo.claim_stale_pending_replay(
                    session,
                    idempotency_key=target.idempotency_key,
                    claim_ttl_seconds=_PENDING_REPLAY_CLAIM_TTL_SECONDS,
                )
                if claimed:
                    if retry_deferred:
                        row.failure_code = None
                        row.failure_reason = None
                    return PrivateTournamentDeliveryPreparation(
                        should_send=True,
                        status="RETRY",
                        created=False,
                    )
            return PrivateTournamentDeliveryPreparation(
                should_send=False,
                status="RETRY",
                created=False,
            )
        return PrivateTournamentDeliveryPreparation(
            should_send=True,
            status=current_status,
            created=created,
        )


async def record_private_tournament_delivery_failure(
    target: PrivateTournamentDeliveryTarget,
    exc: Exception,
) -> TelegramDeliveryExceptionOutcome:
    classified = classify_telegram_delivery_exception(exc)
    if classified is None:
        raise exc
    async with SessionLocal.begin() as session:
        if classified.status == "RETRY":
            retry_after_seconds = max(1, int(classified.retry_after_seconds or 1))
            row = await TelegramDeliveryAttemptsRepo.get_by_idempotency_key(
                session,
                idempotency_key=target.idempotency_key,
            )
            if row is None:
                raise RuntimeError("private tournament retry lease was lost")
            row.failure_code = _RETRY_NEEDED_FAILURE_CODE
            row.failure_reason = f"telegram retry needed after {retry_after_seconds}s"
            deferred = await TelegramDeliveryAttemptsRepo.defer_retry_after(
                session,
                idempotency_key=target.idempotency_key,
                retry_after_seconds=retry_after_seconds,
                claim_ttl_seconds=_PENDING_REPLAY_CLAIM_TTL_SECONDS,
            )
            if not deferred:
                raise RuntimeError("private tournament retry lease was lost")
            return TelegramDeliveryExceptionOutcome(
                status="RETRY",
                retry_after_seconds=retry_after_seconds,
            )
        if classified.failure is None:
            raise exc
        failed = await TelegramDeliveryAttemptsRepo.mark_failed(
            session,
            idempotency_key=target.idempotency_key,
            failure=classified.failure,
        )
        if not failed:
            raise RuntimeError("private tournament failure lease was lost")
        return classified


async def record_private_tournament_delivery_skipped(
    target: PrivateTournamentDeliveryTarget,
    *,
    failure_code: str,
    failure_reason: str,
) -> None:
    async with SessionLocal.begin() as session:
        skipped = await TelegramDeliveryAttemptsRepo.mark_skipped(
            session,
            idempotency_key=target.idempotency_key,
            failure_code=failure_code,
            failure_reason=failure_reason,
        )
        if not skipped:
            raise RuntimeError("private tournament skip lease was lost")


__all__ = [
    "PrivateTournamentDeliveryPreparation",
    "PrivateTournamentStandingsFence",
    "prepare_private_tournament_delivery",
    "persist_private_tournament_sent_message",
    "record_private_tournament_delivery_failure",
    "record_private_tournament_delivery_skipped",
]
