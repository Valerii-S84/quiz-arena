from __future__ import annotations

from urllib.parse import quote_plus

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
    show_proof_card: bool = False,
    share_url: str | None = None,
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
    if show_proof_card:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🧾 Proof Card nochmal",
                    callback_data=f"daily:cup:proof:{tournament_id}",
                )
            ]
        )
    if show_share_result:
        if share_url:
            rows.append([InlineKeyboardButton(text="📤 JETZT TEILEN", url=share_url)])
            rows.append(
                [
                    InlineKeyboardButton(
                        text="✅ Geteilt",
                        callback_data=f"daily:cup:share:{tournament_id}",
                    )
                ]
            )
        else:
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


def build_daily_cup_share_keyboard(
    *,
    tournament_id: str,
    share_url: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if share_url:
        rows.append([InlineKeyboardButton(text="📤 JETZT TEILEN", url=share_url)])
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Geteilt",
                    callback_data=f"daily:cup:share:{tournament_id}",
                )
            ]
        )
    else:
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


def build_daily_cup_share_url(*, base_link: str, share_text: str) -> str:
    return (
        "https://t.me/share/url" f"?url={quote_plus(base_link)}" f"&text={quote_plus(share_text)}"
    )


def build_daily_cup_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Aktualisieren", callback_data="daily:cup:menu")],
            [InlineKeyboardButton(text="🏠 Menü", callback_data="home:open")],
        ]
    )
