from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiogram.types import BufferedInputFile

from app.workers.tasks.tournaments_proof_cards_models import (
    TournamentProofCardAttemptResult,
    TournamentProofCardContext,
)


@dataclass(frozen=True, slots=True)
class TournamentProofCardSendServices:
    session_factory: Any
    participants_repo: Any
    bot: Any
    build_caption_fn: Callable[..., str]
    render_card_fn: Callable[..., bytes]
    logger: Any


@dataclass(frozen=True, slots=True)
class TournamentProofCardSendRequest:
    context: TournamentProofCardContext
    tournament_id: str
    now_utc: datetime
    user_id: int
    chat_id: int
    explicit_resend: bool


@dataclass(frozen=True, slots=True)
class _CachedCardSend:
    user_id: int
    chat_id: int
    caption: str
    cached_file_id: str
    already_sent: bool


async def _set_sent_if_needed(
    *,
    services: TournamentProofCardSendServices,
    session: Any,
    context: TournamentProofCardContext,
    user_id: int,
    already_sent: bool,
) -> None:
    if already_sent:
        return
    await services.participants_repo.set_proof_card_sent(
        session,
        tournament_id=context.parsed_tournament_id,
        user_id=user_id,
    )


async def _load_participant_row(
    *,
    services: TournamentProofCardSendServices,
    session: Any,
    request: TournamentProofCardSendRequest,
) -> Any | None:
    return await services.participants_repo.get_for_tournament_user_for_update(
        session,
        tournament_id=request.context.parsed_tournament_id,
        user_id=request.user_id,
        skip_locked=not request.explicit_resend,
    )


async def _send_cached_card(
    *,
    services: TournamentProofCardSendServices,
    session: Any,
    context: TournamentProofCardContext,
    cached_send: _CachedCardSend,
) -> TournamentProofCardAttemptResult:
    await services.bot.send_photo(
        chat_id=cached_send.chat_id,
        photo=cached_send.cached_file_id,
        caption=cached_send.caption,
    )
    await _set_sent_if_needed(
        services=services,
        session=session,
        context=context,
        user_id=cached_send.user_id,
        already_sent=cached_send.already_sent,
    )
    return TournamentProofCardAttemptResult(sent=True, cached_reused=True, failed=False)


async def _send_rendered_card(
    *,
    services: TournamentProofCardSendServices,
    session: Any,
    request: TournamentProofCardSendRequest,
) -> None:
    context = request.context
    user_id = request.user_id
    place = context.standings_user_ids.index(user_id) + 1
    points = context.points_by_user.get(user_id, "0")
    card_png = services.render_card_fn(
        player_label=context.user_labels.get(user_id, "Spieler"),
        place=place,
        points=points,
        format_label=context.tournament_format,
        completed_at=request.now_utc,
        tournament_name=context.tournament.name,
        rounds_played=context.tournament.current_round,
    )
    message = await services.bot.send_photo(
        chat_id=request.chat_id,
        photo=BufferedInputFile(
            card_png,
            filename=f"tournament_{request.tournament_id}_{user_id}.png",
        ),
        caption=services.build_caption_fn(place=place, points=points),
    )
    await services.participants_repo.set_proof_card_sent(
        session,
        tournament_id=context.parsed_tournament_id,
        user_id=user_id,
    )
    if message.photo:
        await services.participants_repo.set_proof_card_file_id_if_missing(
            session,
            tournament_id=context.parsed_tournament_id,
            user_id=user_id,
            file_id=message.photo[-1].file_id,
        )


async def _send_locked_participant_card(
    *,
    services: TournamentProofCardSendServices,
    session: Any,
    request: TournamentProofCardSendRequest,
    participant_row: Any,
) -> TournamentProofCardAttemptResult:
    context = request.context
    already_sent = bool(participant_row.proof_card_sent)
    if already_sent and not request.explicit_resend:
        return TournamentProofCardAttemptResult(sent=False, cached_reused=False, failed=False)

    place = context.standings_user_ids.index(request.user_id) + 1
    points = context.points_by_user.get(request.user_id, "0")
    caption = services.build_caption_fn(place=place, points=points)
    if participant_row.proof_card_file_id:
        return await _send_cached_card(
            services=services,
            session=session,
            context=context,
            cached_send=_CachedCardSend(
                user_id=request.user_id,
                chat_id=request.chat_id,
                caption=caption,
                cached_file_id=participant_row.proof_card_file_id,
                already_sent=already_sent,
            ),
        )

    await _send_rendered_card(services=services, session=session, request=request)
    return TournamentProofCardAttemptResult(sent=True, cached_reused=False, failed=False)


async def send_tournament_proof_card_for_user(
    *,
    request: TournamentProofCardSendRequest,
    services: TournamentProofCardSendServices,
) -> TournamentProofCardAttemptResult:
    try:
        async with services.session_factory.begin() as session:
            participant_row = await _load_participant_row(
                services=services,
                session=session,
                request=request,
            )
            if participant_row is None:
                return TournamentProofCardAttemptResult(
                    sent=False,
                    cached_reused=False,
                    failed=request.explicit_resend,
                    retry_needed=not request.explicit_resend,
                )
            return await _send_locked_participant_card(
                services=services,
                session=session,
                request=request,
                participant_row=participant_row,
            )
    except Exception as exc:
        services.logger.warning(
            "private_tournament_proof_card_send_failed",
            tournament_id=request.tournament_id,
            user_id=request.user_id,
            error_type=type(exc).__name__,
        )
        return TournamentProofCardAttemptResult(sent=False, cached_reused=False, failed=True)
