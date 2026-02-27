from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.tournament_views import format_points
from app.bot.keyboards.tournament import (
    build_tournament_created_keyboard,
    build_tournament_share_keyboard,
)
from app.bot.texts.de import TEXTS_DE


async def handle_tournament_create_from_format(
    callback: CallbackQuery,
    *,
    rounds: int,
    session_local,
    user_onboarding_service,
    tournament_service,
    build_tournament_invite_link,
    emit_analytics_event,
    event_source_bot: str,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    now_utc = datetime.now(timezone.utc)
    format_code = "QUICK_12" if int(rounds) >= 12 else "QUICK_5"
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        tournament = await tournament_service.create_private_tournament(
            session,
            created_by=snapshot.user_id,
            format_code=format_code,
            now_utc=now_utc,
        )
        await emit_analytics_event(
            session,
            event_type="private_tournament_created",
            source=event_source_bot,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload={"format": tournament.format, "invited_count": 0},
        )
    invite_link = await build_tournament_invite_link(callback, invite_code=tournament.invite_code)
    if not invite_link:
        await callback.message.answer(TEXTS_DE["msg.system.error"])
        await callback.answer()
        return
    await callback.message.answer(
        TEXTS_DE["msg.tournament.created"],
        reply_markup=build_tournament_created_keyboard(
            invite_link=invite_link,
            tournament_id=str(tournament.tournament_id),
            can_start=False,
        ),
    )
    await callback.answer()


async def handle_tournament_share_result(
    callback: CallbackQuery,
    *,
    tournament_id: UUID,
    session_local,
    user_onboarding_service,
    tournament_service,
    build_tournament_share_result_url,
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
        lobby = await tournament_service.get_private_tournament_lobby_by_id(
            session,
            tournament_id=tournament_id,
            viewer_user_id=snapshot.user_id,
        )
        if not lobby.viewer_joined or lobby.tournament.status != "COMPLETED":
            await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
            return
        participant_ids = [item.user_id for item in lobby.participants]
        place = participant_ids.index(snapshot.user_id) + 1
        points = format_points(
            next(item.score for item in lobby.participants if item.user_id == snapshot.user_id)
        )
        await emit_analytics_event(
            session,
            event_type="private_tournament_result_shared",
            source=event_source_bot,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload={
                "tournament_id": str(tournament_id),
                "place": place,
                "score": points,
            },
        )
    share_url = await build_tournament_share_result_url(
        callback,
        share_text=f"🏆 Turnier beendet! Ich bin #{place} mit {points} Pkt.",
    )
    if share_url is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.tournament.share.ready"],
        reply_markup=build_tournament_share_keyboard(
            share_url=share_url,
            tournament_id=str(tournament_id),
        ),
    )
    await callback.answer()
