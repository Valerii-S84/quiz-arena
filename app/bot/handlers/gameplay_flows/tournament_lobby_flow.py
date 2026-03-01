from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.handlers import gameplay_tournament_notifications
from app.bot.handlers.gameplay_flows.tournament_views import (
    render_tournament_lobby,
    resolve_participant_labels,
)
from app.bot.texts.de import TEXTS_DE


def _build_creator_start_markup(*, tournament_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ Turnier starten",
                    callback_data=f"friend:tournament:start:{tournament_id}",
                )
            ]
        ]
    )


async def handle_tournament_join_by_invite(
    callback: CallbackQuery,
    *,
    invite_code: str,
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
        join_result = await tournament_service.join_private_tournament_by_code(
            session,
            user_id=snapshot.user_id,
            invite_code=invite_code,
            now_utc=now_utc,
        )
        lobby = await tournament_service.get_private_tournament_lobby_by_invite_code(
            session,
            invite_code=invite_code,
            viewer_user_id=snapshot.user_id,
        )
        labels = await resolve_participant_labels(
            participants=lobby.participants,
            users_repo=users_repo,
            session=session,
        )
        creator = None
        if lobby.tournament.created_by is not None:
            creator = await users_repo.get_by_id(session, lobby.tournament.created_by)
        if join_result.joined_now:
            await emit_analytics_event(
                session,
                event_type="private_tournament_joined",
                source=event_source_bot,
                happened_at=now_utc,
                user_id=snapshot.user_id,
                payload={"tournament_id": str(lobby.tournament.tournament_id)},
            )
    if join_result.joined_now:
        await callback.message.answer(TEXTS_DE["msg.tournament.joined"])
        bot = callback.bot
        assert bot is not None
        if (
            creator is not None
            and int(creator.telegram_user_id) != int(callback.from_user.id)
            and int(creator.telegram_user_id) != int(snapshot.user_id)
        ):
            participant_count = len(lobby.participants)
            start_markup = (
                _build_creator_start_markup(tournament_id=str(lobby.tournament.tournament_id))
                if participant_count >= 2
                else None
            )
            try:
                await bot.send_message(
                    chat_id=int(creator.telegram_user_id),
                    text=(
                        f"✅ {(callback.from_user.first_name or 'Ein Spieler')} hat dein Turnier betreten!\n"
                        f"Teilnehmer: {participant_count}/{lobby.tournament.max_participants}\n\n"
                        + (
                            "[▶️ Turnier starten]"
                            if participant_count >= 2
                            else "Warte auf mehr Spieler..."
                        )
                    ),
                    reply_markup=start_markup,
                )
            except TelegramAPIError:
                creator = None
    await render_tournament_lobby(callback, lobby=lobby, user_id=snapshot.user_id, labels=labels)
    await callback.answer()


async def handle_tournament_view(
    callback: CallbackQuery,
    *,
    tournament_id: UUID,
    session_local,
    user_onboarding_service,
    tournament_service,
    users_repo,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
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
        labels = await resolve_participant_labels(
            participants=lobby.participants,
            users_repo=users_repo,
            session=session,
        )
    await render_tournament_lobby(callback, lobby=lobby, user_id=snapshot.user_id, labels=labels)
    await callback.answer()


async def handle_tournament_copy_link(
    callback: CallbackQuery,
    *,
    tournament_id: UUID,
    session_local,
    user_onboarding_service,
    tournament_service,
    build_tournament_invite_link,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
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
    invite_link = await build_tournament_invite_link(
        callback, invite_code=lobby.tournament.invite_code
    )
    if invite_link is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(invite_link)
    await callback.answer(TEXTS_DE["msg.friend.challenge.link.copied"])


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
