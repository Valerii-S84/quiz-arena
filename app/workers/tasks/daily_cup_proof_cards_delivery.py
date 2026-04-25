from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.workers.tasks.daily_cup_proof_card_sender import send_daily_cup_proof_card
from app.workers.tasks.tournaments_proof_card_render import render_tournament_proof_card_png


@dataclass(frozen=True, slots=True)
class DailyCupProofCardDeliveryResult:
    sent: int
    cached_reused: int
    failed: int


@dataclass(frozen=True, slots=True)
class DailyCupProofCardAttemptResult:
    sent: bool
    cached_reused: bool
    failed: bool
    retry_needed: bool = False


def _queue_retry_after_lock_skip(
    *,
    tournament_id: str,
    user_id: int,
    retry_delay_seconds: int,
    enqueue_retry_fn: Callable[..., bool] | None,
    logger: Any,
) -> None:
    if enqueue_retry_fn is None:
        return
    queued = enqueue_retry_fn(
        tournament_id=tournament_id,
        user_id=user_id,
        delay_seconds=retry_delay_seconds,
    )
    if not queued:
        return
    logger.info(
        "daily_cup_proof_card_retry_queued",
        tournament_id=tournament_id,
        user_id=user_id,
        reason="participant_row_lock_skipped",
    )


async def _deliver_proof_card_for_user(
    *,
    context: Any,
    bot: Any,
    tournament_id: str,
    user_id: int,
    chat_id: int,
    now_utc: datetime,
    session_factory: Any,
    participants_repo: Any,
    send_proof_card_fn: Callable[..., Any],
    render_card_png: Callable[..., bytes],
    logger: Any,
) -> DailyCupProofCardAttemptResult:
    try:
        async with session_factory.begin() as session:
            participant_row = await participants_repo.get_for_tournament_user_for_update(
                session,
                tournament_id=context.parsed_tournament_id,
                user_id=user_id,
                skip_locked=True,
            )
            if participant_row is None:
                return DailyCupProofCardAttemptResult(
                    sent=False,
                    cached_reused=False,
                    failed=False,
                    retry_needed=True,
                )
            if participant_row.proof_card_sent:
                return DailyCupProofCardAttemptResult(
                    sent=False,
                    cached_reused=False,
                    failed=False,
                )

            place = context.standings_user_ids.index(user_id) + 1
            points = context.points_by_user.get(user_id, "0")
            delivered, reused_cached, file_id = await send_proof_card_fn(
                bot=bot,
                tournament_id=tournament_id,
                user_id=user_id,
                chat_id=chat_id,
                place=place,
                points=points,
                participants_total=context.participants_total,
                cached_file_id=participant_row.proof_card_file_id,
                player_label=context.user_labels.get(user_id, "Spieler"),
                now_utc=now_utc,
                rounds_played=context.rounds_played,
                render_card_png=render_card_png,
            )
            if not delivered:
                return DailyCupProofCardAttemptResult(
                    sent=False,
                    cached_reused=False,
                    failed=False,
                )

            await participants_repo.set_proof_card_sent(
                session,
                tournament_id=context.parsed_tournament_id,
                user_id=user_id,
            )
            if file_id is not None:
                await participants_repo.set_proof_card_file_id_if_missing(
                    session,
                    tournament_id=context.parsed_tournament_id,
                    user_id=user_id,
                    file_id=file_id,
                )
    except Exception as exc:
        logger.warning(
            "daily_cup_proof_card_send_failed",
            tournament_id=tournament_id,
            user_id=user_id,
            error_type=type(exc).__name__,
        )
        return DailyCupProofCardAttemptResult(sent=False, cached_reused=False, failed=True)

    return DailyCupProofCardAttemptResult(
        sent=True,
        cached_reused=bool(reused_cached),
        failed=False,
    )


async def deliver_daily_cup_proof_cards(
    *,
    context: Any,
    bot: Any,
    tournament_id: str,
    now_utc: datetime,
    session_factory: Any,
    participants_repo: Any,
    send_proof_card_fn: Callable[..., Any],
    enqueue_retry_fn: Callable[..., bool] | None = None,
    retry_delay_seconds: int = 2,
    render_card_png: Callable[..., bytes] = render_tournament_proof_card_png,
    logger: Any,
) -> DailyCupProofCardDeliveryResult:
    sent = 0
    cached_reused = 0
    failed = 0

    for row in context.participants:
        current_user_id = int(row.user_id)
        chat_id = context.telegram_targets.get(current_user_id)
        if chat_id is None:
            failed += 1
            continue
        attempt = await _deliver_proof_card_for_user(
            context=context,
            bot=bot,
            tournament_id=tournament_id,
            user_id=current_user_id,
            chat_id=chat_id,
            now_utc=now_utc,
            session_factory=session_factory,
            participants_repo=participants_repo,
            send_proof_card_fn=send_proof_card_fn,
            render_card_png=render_card_png,
            logger=logger,
        )
        if attempt.retry_needed:
            _queue_retry_after_lock_skip(
                tournament_id=tournament_id,
                user_id=current_user_id,
                retry_delay_seconds=retry_delay_seconds,
                enqueue_retry_fn=enqueue_retry_fn,
                logger=logger,
            )
        sent += int(attempt.sent)
        cached_reused += int(attempt.cached_reused)
        failed += int(attempt.failed)

    return DailyCupProofCardDeliveryResult(
        sent=sent,
        cached_reused=cached_reused,
        failed=failed,
    )


__all__ = [
    "DailyCupProofCardDeliveryResult",
    "deliver_daily_cup_proof_cards",
    "send_daily_cup_proof_card",
]
