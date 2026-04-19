from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from aiogram.types import CallbackQuery

from app.bot.handlers import gameplay_tournament_notifications
from app.bot.texts.de import TEXTS_DE

from .tournament_views import render_tournament_lobby, resolve_participant_labels


async def handle_tournament_start(
    callback: CallbackQuery,
    *,
    tournament_id: UUID,
    session_local,
    user_onboarding_service,
    tournament_service,
    users_repo,
    emit_analytics_event,
    event_source_bot: str,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        await tournament_service.start_private_tournament(
            session,
            creator_user_id=snapshot.user_id,
            tournament_id=tournament_id,
            now_utc=now_utc,
        )
        lobby = await tournament_service.get_private_tournament_lobby_by_id(
            session,
            tournament_id=tournament_id,
            viewer_user_id=snapshot.user_id,
        )
        labels = await resolve_participant_labels(
            participants=lobby.participants,
            users_repo=users_repo,
            session=session,
        )
        await emit_analytics_event(
            session,
            event_type="private_tournament_started",
            source=event_source_bot,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload={"tournament_id": str(tournament_id)},
        )
    await callback.message.answer(TEXTS_DE["msg.tournament.started"])
    await render_tournament_lobby(callback, lobby=lobby, user_id=snapshot.user_id, labels=labels)
    gameplay_tournament_notifications.enqueue_tournament_round_messaging(
        tournament_id=str(tournament_id)
    )
    await callback.answer()
