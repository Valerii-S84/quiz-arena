from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.game.tournaments.constants import TOURNAMENT_STATUS_COMPLETED, TOURNAMENT_TYPE_PRIVATE
from app.workers.tasks.tournaments_proof_cards_models import (
    TournamentProofCardContext,
    TournamentProofCardContextRequest,
    TournamentProofCardContextServices,
    TournamentProofCardDeliveryRequest,
    TournamentProofCardDeliveryResult,
    TournamentProofCardDeliveryServices,
)
from app.workers.tasks.tournaments_proof_cards_sender import (
    TournamentProofCardSendRequest,
    TournamentProofCardSendServices,
    send_tournament_proof_card_for_user,
)


@dataclass(slots=True)
class _DeliveryCounters:
    sent: int = 0
    cached_reused: int = 0
    failed: int = 0

    def record_attempt(self, *, attempt: Any) -> None:
        self.sent += int(attempt.sent)
        self.cached_reused += int(attempt.cached_reused)
        self.failed += int(attempt.failed)

    def to_result(self) -> TournamentProofCardDeliveryResult:
        return TournamentProofCardDeliveryResult(
            sent=self.sent,
            cached_reused=self.cached_reused,
            failed=self.failed,
        )


def _queue_retry_after_lock_skip(
    *,
    tournament_id: str,
    user_id: int,
    lock_retry_attempt: int,
    retry_delay_seconds: int,
    enqueue_retry_fn: Callable[..., bool] | None,
    logger: Any,
) -> bool:
    if enqueue_retry_fn is None:
        return False
    queued = enqueue_retry_fn(
        tournament_id=tournament_id,
        user_id=user_id,
        explicit_resend=False,
        delay_seconds=retry_delay_seconds,
        lock_retry_attempt=lock_retry_attempt + 1,
    )
    if not queued:
        return False
    logger.info(
        "private_tournament_proof_card_retry_queued",
        tournament_id=tournament_id,
        user_id=user_id,
        retry_attempt=lock_retry_attempt + 1,
        reason="participant_row_lock_skipped",
    )
    return True


def _record_retry_result(
    *,
    counters: _DeliveryCounters,
    tournament_id: str,
    user_id: int,
    lock_retry_attempt: int,
    retry_delay_seconds: int,
    enqueue_retry_fn: Callable[..., bool] | None,
    logger: Any,
) -> None:
    queued = _queue_retry_after_lock_skip(
        tournament_id=tournament_id,
        user_id=user_id,
        lock_retry_attempt=lock_retry_attempt,
        retry_delay_seconds=retry_delay_seconds,
        enqueue_retry_fn=enqueue_retry_fn,
        logger=logger,
    )
    counters.failed += int(not queued)


async def load_proof_card_context(
    *,
    request: TournamentProofCardContextRequest,
    services: TournamentProofCardContextServices,
) -> TournamentProofCardContext | None:
    tournament = await services.tournaments_repo.get_by_id(
        request.session,
        request.parsed_tournament_id,
    )
    if (
        tournament is None
        or tournament.type != TOURNAMENT_TYPE_PRIVATE
        or tournament.status != TOURNAMENT_STATUS_COMPLETED
    ):
        return None
    all_participants = await services.participants_repo.list_for_tournament(
        request.session,
        tournament_id=request.parsed_tournament_id,
    )
    if not all_participants:
        return None
    participants = (
        [item for item in all_participants if int(item.user_id) == request.user_id]
        if request.user_id is not None
        else all_participants
    )
    users = await services.users_repo.list_by_ids(
        request.session,
        [int(item.user_id) for item in all_participants],
    )
    return TournamentProofCardContext(
        parsed_tournament_id=request.parsed_tournament_id,
        tournament=tournament,
        participants=participants,
        participants_total=len(all_participants),
        tournament_format=services.format_tournament_format_fn(tournament.format),
        standings_user_ids=[int(item.user_id) for item in all_participants],
        points_by_user={
            int(item.user_id): services.format_points_fn(item.score) for item in all_participants
        },
        telegram_targets={int(user.id): int(user.telegram_user_id) for user in users},
        user_labels={
            int(user.id): services.format_user_label_fn(
                username=user.username,
                first_name=user.first_name,
            )
            for user in users
        },
    )


async def deliver_proof_cards(
    *,
    request: TournamentProofCardDeliveryRequest,
    services: TournamentProofCardDeliveryServices,
) -> TournamentProofCardDeliveryResult:
    bot = services.build_bot_fn()
    counters = _DeliveryCounters()
    send_services = TournamentProofCardSendServices(
        session_factory=services.session_factory,
        participants_repo=services.participants_repo,
        bot=bot,
        build_caption_fn=services.build_caption_fn,
        render_card_fn=services.render_card_fn,
        logger=services.logger,
    )
    try:
        for row in request.context.participants:
            current_user_id = int(row.user_id)
            chat_id = request.context.telegram_targets.get(current_user_id)
            if chat_id is None:
                counters.failed += 1
                continue
            attempt = await send_tournament_proof_card_for_user(
                request=TournamentProofCardSendRequest(
                    context=request.context,
                    tournament_id=request.tournament_id,
                    now_utc=request.now_utc,
                    user_id=current_user_id,
                    chat_id=chat_id,
                    explicit_resend=request.explicit_resend,
                ),
                services=send_services,
            )
            if attempt.retry_needed:
                _record_retry_result(
                    counters=counters,
                    tournament_id=request.tournament_id,
                    user_id=current_user_id,
                    lock_retry_attempt=request.lock_retry_attempt,
                    retry_delay_seconds=request.retry_delay_seconds,
                    enqueue_retry_fn=services.enqueue_retry_fn,
                    logger=services.logger,
                )
                continue
            counters.record_attempt(attempt=attempt)
    finally:
        await bot.session.close()

    return counters.to_result()


__all__ = [
    "TournamentProofCardContext",
    "TournamentProofCardContextRequest",
    "TournamentProofCardContextServices",
    "TournamentProofCardDeliveryRequest",
    "TournamentProofCardDeliveryResult",
    "TournamentProofCardDeliveryServices",
    "deliver_proof_cards",
    "load_proof_card_context",
]
