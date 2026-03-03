from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.daily_cup_views import render_daily_cup_lobby
from app.bot.handlers.gameplay_flows.tournament_views import resolve_participant_labels
from app.bot.keyboards.daily_cup import build_daily_cup_menu_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.tournaments.daily_cup_user_status import DailyCupUserStatus, get_daily_cup_status_for_user

_MENU_SPAM_COOLDOWN = timedelta(seconds=2)
_last_opened_at_by_user_id: dict[int, datetime] = {}


def _is_menu_spam(*, user_id: int, now_utc: datetime) -> bool:
    previous = _last_opened_at_by_user_id.get(user_id)
    _last_opened_at_by_user_id[user_id] = now_utc
    if previous is None:
        return False
    return now_utc - previous < _MENU_SPAM_COOLDOWN


async def handle_daily_cup_menu(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    tournament_service,
    users_repo,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    lobby = None
    labels: dict[int, str] = {}
    viewer_user_id: int | None = None
    text_key = "msg.daily_cup.no_tournament"
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        if _is_menu_spam(user_id=snapshot.user_id, now_utc=now_utc):
            await callback.answer(TEXTS_DE["msg.daily_cup.menu.already_open"], show_alert=False)
            return
        viewer_user_id = snapshot.user_id
        status_snapshot = await get_daily_cup_status_for_user(
            session,
            user_id=snapshot.user_id,
            now_utc=now_utc,
        )
        if (
            status_snapshot.tournament is not None
            and status_snapshot.status not in {DailyCupUserStatus.NO_TOURNAMENT}
        ):
            if status_snapshot.status == DailyCupUserStatus.NOT_PARTICIPANT:
                text_key = "msg.daily_cup.not_participant"
            else:
                lobby = await tournament_service.get_daily_cup_lobby_by_id(
                    session,
                    tournament_id=status_snapshot.tournament.id,
                    viewer_user_id=snapshot.user_id,
                )
                labels = await resolve_participant_labels(
                    participants=lobby.participants,
                    users_repo=users_repo,
                    session=session,
                )

    if lobby is not None and viewer_user_id is not None:
        await render_daily_cup_lobby(
            callback,
            lobby=lobby,
            user_id=viewer_user_id,
            labels=labels,
            replace_current_message=True,
        )
    else:
        await callback.message.answer(
            TEXTS_DE[text_key],
            reply_markup=build_daily_cup_menu_keyboard(),
        )
    await callback.answer()


__all__ = ["handle_daily_cup_menu"]
