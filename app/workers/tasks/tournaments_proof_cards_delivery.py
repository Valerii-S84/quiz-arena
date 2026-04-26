from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from aiogram.types import BufferedInputFile

from app.game.tournaments.constants import TOURNAMENT_STATUS_COMPLETED, TOURNAMENT_TYPE_PRIVATE


@dataclass(frozen=True, slots=True)
class TournamentProofCardContext:
    parsed_tournament_id: UUID
    tournament: Any
    participants: list[Any]
    participants_total: int
    tournament_format: str
    standings_user_ids: list[int]
    points_by_user: dict[int, str]
    telegram_targets: dict[int, int]
    user_labels: dict[int, str]


@dataclass(frozen=True, slots=True)
class TournamentProofCardDeliveryResult:
    sent: int
    cached_reused: int
    failed: int


@dataclass(frozen=True, slots=True)
class TournamentProofCardAttemptResult:
    sent: bool
    cached_reused: bool
    failed: bool
    retry_needed: bool = False


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


async def load_proof_card_context(
    *,
    session: Any,
    parsed_tournament_id: UUID,
    user_id: int | None,
    tournaments_repo: Any,
    participants_repo: Any,
    users_repo: Any,
    format_points_fn: Callable[..., str],
    format_tournament_format_fn: Callable[..., str],
    format_user_label_fn: Callable[..., str],
) -> TournamentProofCardContext | None:
    tournament = await tournaments_repo.get_by_id(session, parsed_tournament_id)
    if (
        tournament is None
        or tournament.type != TOURNAMENT_TYPE_PRIVATE
        or tournament.status != TOURNAMENT_STATUS_COMPLETED
    ):
        return None
    all_participants = await participants_repo.list_for_tournament(
        session,
        tournament_id=parsed_tournament_id,
    )
    if not all_participants:
        return None
    participants = (
        [item for item in all_participants if int(item.user_id) == user_id]
        if user_id is not None
        else all_participants
    )
    users = await users_repo.list_by_ids(session, [int(item.user_id) for item in all_participants])
    return TournamentProofCardContext(
        parsed_tournament_id=parsed_tournament_id,
        tournament=tournament,
        participants=participants,
        participants_total=len(all_participants),
        tournament_format=format_tournament_format_fn(tournament.format),
        standings_user_ids=[int(item.user_id) for item in all_participants],
        points_by_user={
            int(item.user_id): format_points_fn(item.score) for item in all_participants
        },
        telegram_targets={int(user.id): int(user.telegram_user_id) for user in users},
        user_labels={
            int(user.id): format_user_label_fn(username=user.username, first_name=user.first_name)
            for user in users
        },
    )


async def deliver_proof_cards(
    *,
    context: TournamentProofCardContext,
    tournament_id: str,
    now_utc: datetime,
    session_factory: Any,
    participants_repo: Any,
    build_bot_fn: Callable[[], Any],
    build_caption_fn: Callable[..., str],
    render_card_fn: Callable[..., bytes],
    explicit_resend: bool,
    enqueue_retry_fn: Callable[..., bool] | None = None,
    lock_retry_attempt: int = 0,
    retry_delay_seconds: int = 2,
    logger: Any,
) -> TournamentProofCardDeliveryResult:
    async def _deliver_for_user(
        *, current_user_id: int, chat_id: int
    ) -> TournamentProofCardAttemptResult:
        try:
            async with session_factory.begin() as session:
                participant_row = await participants_repo.get_for_tournament_user_for_update(
                    session,
                    tournament_id=context.parsed_tournament_id,
                    user_id=current_user_id,
                    skip_locked=not explicit_resend,
                )
                if participant_row is None:
                    return TournamentProofCardAttemptResult(
                        sent=False,
                        cached_reused=False,
                        failed=explicit_resend,
                        retry_needed=not explicit_resend,
                    )

                already_sent = bool(participant_row.proof_card_sent)
                if already_sent and not explicit_resend:
                    return TournamentProofCardAttemptResult(
                        sent=False,
                        cached_reused=False,
                        failed=False,
                    )

                place = context.standings_user_ids.index(current_user_id) + 1
                points = context.points_by_user.get(current_user_id, "0")
                caption = build_caption_fn(place=place, points=points)
                cached_file_id = participant_row.proof_card_file_id
                if cached_file_id:
                    await bot.send_photo(chat_id=chat_id, photo=cached_file_id, caption=caption)
                    if not already_sent:
                        await participants_repo.set_proof_card_sent(
                            session,
                            tournament_id=context.parsed_tournament_id,
                            user_id=current_user_id,
                        )
                    return TournamentProofCardAttemptResult(
                        sent=True,
                        cached_reused=True,
                        failed=False,
                    )

                card_png = render_card_fn(
                    player_label=context.user_labels.get(current_user_id, "Spieler"),
                    place=place,
                    points=points,
                    format_label=context.tournament_format,
                    completed_at=now_utc,
                    tournament_name=context.tournament.name,
                    rounds_played=context.tournament.current_round,
                )
                message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=BufferedInputFile(
                        card_png,
                        filename=f"tournament_{tournament_id}_{current_user_id}.png",
                    ),
                    caption=caption,
                )
                await participants_repo.set_proof_card_sent(
                    session,
                    tournament_id=context.parsed_tournament_id,
                    user_id=current_user_id,
                )
                if message.photo:
                    await participants_repo.set_proof_card_file_id_if_missing(
                        session,
                        tournament_id=context.parsed_tournament_id,
                        user_id=current_user_id,
                        file_id=message.photo[-1].file_id,
                    )
        except Exception as exc:
            logger.warning(
                "private_tournament_proof_card_send_failed",
                tournament_id=tournament_id,
                user_id=current_user_id,
                error_type=type(exc).__name__,
            )
            return TournamentProofCardAttemptResult(sent=False, cached_reused=False, failed=True)

        return TournamentProofCardAttemptResult(sent=True, cached_reused=False, failed=False)

    sent = 0
    cached_reused = 0
    failed = 0

    bot = build_bot_fn()
    try:
        for row in context.participants:
            current_user_id = int(row.user_id)
            chat_id = context.telegram_targets.get(current_user_id)
            if chat_id is None:
                failed += 1
                continue
            attempt = await _deliver_for_user(current_user_id=current_user_id, chat_id=chat_id)
            if attempt.retry_needed:
                queued = _queue_retry_after_lock_skip(
                    tournament_id=tournament_id,
                    user_id=current_user_id,
                    lock_retry_attempt=lock_retry_attempt,
                    retry_delay_seconds=retry_delay_seconds,
                    enqueue_retry_fn=enqueue_retry_fn,
                    logger=logger,
                )
                failed += int(not queued)
                continue
            sent += int(attempt.sent)
            cached_reused += int(attempt.cached_reused)
            failed += int(attempt.failed)
    finally:
        await bot.session.close()

    return TournamentProofCardDeliveryResult(
        sent=sent,
        cached_reused=cached_reused,
        failed=failed,
    )


__all__ = [
    "TournamentProofCardContext",
    "TournamentProofCardDeliveryResult",
    "deliver_proof_cards",
    "load_proof_card_context",
]
