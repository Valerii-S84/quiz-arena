from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_daily_cup_registration_keyboard(*, tournament_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ich bin dabei!",
                    callback_data=f"daily:cup:join:{tournament_id}",
                )
            ]
        ]
    )


def build_daily_cup_lobby_keyboard(
    *,
    tournament_id: str,
    can_join: bool,
    play_challenge_id: str | None,
    show_share_result: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_join:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Ich bin dabei!",
                    callback_data=f"daily:cup:join:{tournament_id}",
                )
            ]
        )
    if play_challenge_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text="▶️ Jetzt spielen!",
                    callback_data=f"friend:next:{play_challenge_id}",
                )
            ]
        )
    if show_share_result:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📤 Ergebnis teilen",
                    callback_data=f"daily:cup:share:{tournament_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Aktualisieren",
                callback_data=f"daily:cup:view:{tournament_id}",
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="🏠 Menü", callback_data="home:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_daily_cup_share_keyboard(*, share_url: str, tournament_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 JETZT TEILEN", url=share_url)],
            [
                InlineKeyboardButton(
                    text="🔄 Aktualisieren",
                    callback_data=f"daily:cup:view:{tournament_id}",
                )
            ],
            [InlineKeyboardButton(text="🏠 Menü", callback_data="home:open")],
        ]
    )
