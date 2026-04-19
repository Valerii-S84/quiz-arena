from __future__ import annotations

from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup


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


def _should_notify_creator(*, creator, callback_user_id: int, viewer_user_id: int) -> bool:
    return (
        creator is not None
        and int(creator.telegram_user_id) != int(callback_user_id)
        and int(creator.telegram_user_id) != int(viewer_user_id)
    )


def _build_creator_join_text(
    *, callback: CallbackQuery, participant_count: int, max_participants: int
) -> str:
    return (
        f"✅ {(callback.from_user.first_name or 'Ein Spieler')} hat dein Turnier betreten!\n"
        f"Teilnehmer: {participant_count}/{max_participants}\n\n"
        + ("[▶️ Turnier starten]" if participant_count >= 2 else "Warte auf mehr Spieler...")
    )


async def notify_creator_about_join(
    *,
    callback: CallbackQuery,
    creator,
    lobby,
    viewer_user_id: int,
) -> None:
    bot = callback.bot
    assert bot is not None
    if not _should_notify_creator(
        creator=creator,
        callback_user_id=callback.from_user.id,
        viewer_user_id=viewer_user_id,
    ):
        return
    participant_count = len(lobby.participants)
    start_markup = (
        _build_creator_start_markup(tournament_id=str(lobby.tournament.tournament_id))
        if participant_count >= 2
        else None
    )
    try:
        await bot.send_message(
            chat_id=int(creator.telegram_user_id),
            text=_build_creator_join_text(
                callback=callback,
                participant_count=participant_count,
                max_participants=lobby.tournament.max_participants,
            ),
            reply_markup=start_markup,
        )
    except TelegramAPIError:
        return
