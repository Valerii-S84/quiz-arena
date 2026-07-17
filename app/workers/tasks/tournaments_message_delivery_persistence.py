from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.db.repo.telegram_delivery_attempts_repo import TelegramDeliveryAttemptsRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.session import SessionLocal
from app.services.telegram_delivery_outcomes import classify_telegram_delivery_exception
from app.workers.tasks.tournaments_messaging_delivery_targets import (
    SKIP_CODE_EDIT_REPLACED_BY_SEND,
    SKIP_CODE_NO_CHAT,
    PrivateTournamentDeliveryTarget,
)

_PENDING_REPLAY_CLAIM_TTL_SECONDS = 300


@dataclass(frozen=True, slots=True)
class PrivateTournamentStandingsFence:
    tournament_id: UUID
    user_id: int
    expected_message_id: int | None
    expected_status: str
    expected_round: int


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
            if target.pending_replay_safe:
                claimed = await TelegramDeliveryAttemptsRepo.claim_stale_pending_replay(
                    session,
                    idempotency_key=target.idempotency_key,
                    claim_ttl_seconds=_PENDING_REPLAY_CLAIM_TTL_SECONDS,
                )
                if claimed:
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
) -> str:
    classified = classify_telegram_delivery_exception(exc)
    if classified is None:
        raise exc
    async with SessionLocal.begin() as session:
        if classified.status == "RETRY":
            deferred = await TelegramDeliveryAttemptsRepo.defer_retry_after(
                session,
                idempotency_key=target.idempotency_key,
                retry_after_seconds=classified.retry_after_seconds or 1,
                claim_ttl_seconds=_PENDING_REPLAY_CLAIM_TTL_SECONDS,
            )
            if not deferred:
                raise RuntimeError("private tournament retry lease was lost")
            return "RETRY"
        if classified.failure is None:
            raise exc
        failed = await TelegramDeliveryAttemptsRepo.mark_failed(
            session,
            idempotency_key=target.idempotency_key,
            failure=classified.failure,
        )
        if not failed:
            raise RuntimeError("private tournament failure lease was lost")
        return "FAILED"


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


async def persist_private_tournament_sent_message(
    target: PrivateTournamentDeliveryTarget,
    fence: PrivateTournamentStandingsFence,
    message: Any | int,
    happened_at: datetime,
    *,
    original_target: PrivateTournamentDeliveryTarget | None = None,
) -> int:
    del happened_at
    message_id = int(message if isinstance(message, int) else message.message_id)
    async with SessionLocal.begin() as session:
        persisted = await TournamentParticipantsRepo.compare_and_set_standings_message_id(
            session,
            tournament_id=fence.tournament_id,
            user_id=fence.user_id,
            expected_message_id=fence.expected_message_id,
            message_id=message_id,
            expected_status=fence.expected_status,
            expected_round=fence.expected_round,
        )
        if persisted != 1:
            raise RuntimeError("private tournament standings delivery fence was lost")
        sent = await TelegramDeliveryAttemptsRepo.mark_sent(
            session,
            idempotency_key=target.idempotency_key,
        )
        if not sent:
            raise RuntimeError("private tournament delivery terminal lease was lost")
        if original_target is not None:
            skipped = await TelegramDeliveryAttemptsRepo.mark_skipped(
                session,
                idempotency_key=original_target.idempotency_key,
                failure_code=SKIP_CODE_EDIT_REPLACED_BY_SEND,
                failure_reason="edit delivery replaced by fallback send",
            )
            if not skipped:
                raise RuntimeError("private tournament original edit lease was lost")
    return message_id


__all__ = [
    "PrivateTournamentDeliveryPreparation",
    "PrivateTournamentStandingsFence",
    "prepare_private_tournament_delivery",
    "persist_private_tournament_sent_message",
    "record_private_tournament_delivery_failure",
    "record_private_tournament_delivery_skipped",
]
