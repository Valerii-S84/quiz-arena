from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.daily_cup_views import render_daily_cup_lobby
from app.bot.handlers.gameplay_flows.tournament_views import (
    format_points,
    resolve_participant_labels,
)
from app.bot.keyboards.daily_cup import build_daily_cup_share_keyboard, build_daily_cup_share_url
from app.bot.texts.de import TEXTS_DE
from app.core.telegram_links import public_bot_link


def _message_has_share_url_button(message) -> bool:
    markup = getattr(message, "reply_markup", None)
    if markup is None:
        return False
    for row in markup.inline_keyboard:
        for button in row:
            if button.url and "https://t.me/share/url" in button.url:
                return True
    return False


async def handle_daily_cup_join(
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
        join_result = await tournament_service.join_daily_cup_by_id(
            session,
            user_id=snapshot.user_id,
            tournament_id=tournament_id,
            now_utc=now_utc,
        )
        lobby = await tournament_service.get_daily_cup_lobby_by_id(
            session,
            tournament_id=tournament_id,
            viewer_user_id=snapshot.user_id,
        )
        labels = await resolve_participant_labels(
            participants=lobby.participants,
            users_repo=users_repo,
            session=session,
        )
        if join_result.joined_now:
            await emit_analytics_event(
                session,
                event_type="daily_cup_registered",
                source=event_source_bot,
                happened_at=now_utc,
                user_id=snapshot.user_id,
                payload={"tournament_id": str(tournament_id)},
            )

    if join_result.joined_now:
        await callback.message.answer(
            TEXTS_DE["msg.daily_cup.joined_confirmation"].format(
                participants_total=join_result.participants_total
            )
        )
    else:
        await callback.message.answer(TEXTS_DE["msg.daily_cup.already_joined"])
    await render_daily_cup_lobby(
        callback,
        lobby=lobby,
        user_id=snapshot.user_id,
        labels=labels,
        replace_current_message=True,
    )
    await callback.answer()


async def handle_daily_cup_view(
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
        lobby = await tournament_service.get_daily_cup_lobby_by_id(
            session,
            tournament_id=tournament_id,
            viewer_user_id=snapshot.user_id,
        )
        labels = await resolve_participant_labels(
            participants=lobby.participants,
            users_repo=users_repo,
            session=session,
        )
        if lobby.tournament.status == "COMPLETED" and lobby.viewer_joined:
            await emit_analytics_event(
                session,
                event_type="daily_cup_final_viewed",
                source=event_source_bot,
                happened_at=now_utc,
                user_id=snapshot.user_id,
                payload={"tournament_id": str(tournament_id)},
            )
    await render_daily_cup_lobby(
        callback,
        lobby=lobby,
        user_id=snapshot.user_id,
        labels=labels,
        replace_current_message=True,
    )
    await callback.answer()


async def handle_daily_cup_share_result(
    callback: CallbackQuery,
    *,
    tournament_id: UUID,
    session_local,
    user_onboarding_service,
    tournament_service,
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
        lobby = await tournament_service.get_daily_cup_lobby_by_id(
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
            event_type="daily_cup_result_shared",
            source=event_source_bot,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload={
                "tournament_id": str(tournament_id),
                "place": place,
                "score": points,
            },
        )
    from app.workers.tasks.daily_cup_proof_cards import enqueue_daily_cup_proof_cards

    enqueue_daily_cup_proof_cards(
        tournament_id=str(tournament_id),
        user_id=snapshot.user_id,
        delay_seconds=0,
    )
    share_url = build_daily_cup_share_url(
        base_link=public_bot_link(),
        share_text=TEXTS_DE["msg.daily_cup.share_template"].format(
            place=place,
            total=len(participant_ids),
            points=points,
        ),
    )
    if _message_has_share_url_button(callback.message):
        await callback.answer(TEXTS_DE["msg.daily_cup.share.thanks"], show_alert=False)
        return
    await callback.message.answer(
        TEXTS_DE["msg.daily_cup.share.ready"],
        reply_markup=build_daily_cup_share_keyboard(
            share_url=share_url,
            tournament_id=str(tournament_id),
        ),
    )
    await callback.answer()


async def handle_daily_cup_request_proof_card(
    callback: CallbackQuery,
    *,
    tournament_id: UUID,
    session_local,
    user_onboarding_service,
    tournament_service,
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
        lobby = await tournament_service.get_daily_cup_lobby_by_id(
            session,
            tournament_id=tournament_id,
            viewer_user_id=snapshot.user_id,
        )
        if not lobby.viewer_joined or lobby.tournament.status != "COMPLETED":
            await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
            return
        await emit_analytics_event(
            session,
            event_type="daily_cup_proof_card_requested",
            source=event_source_bot,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload={"tournament_id": str(tournament_id)},
        )
    from app.workers.tasks.daily_cup_proof_cards import enqueue_daily_cup_proof_cards

    enqueue_daily_cup_proof_cards(
        tournament_id=str(tournament_id),
        user_id=snapshot.user_id,
        delay_seconds=0,
    )
    await callback.answer(TEXTS_DE["msg.daily_cup.proof_card.queued"], show_alert=False)
