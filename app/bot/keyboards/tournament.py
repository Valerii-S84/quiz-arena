from __future__ import annotations

from urllib.parse import quote_plus

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_tournament_share_url(*, base_link: str, share_text: str) -> str:
    return (
        "https://t.me/share/url" f"?url={quote_plus(base_link)}" f"&text={quote_plus(share_text)}"
    )


def build_tournament_format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ 5 Fragen", callback_data="friend:tournament:format:5")],
            [InlineKeyboardButton(text="🧠 12 Fragen", callback_data="friend:tournament:format:12")],
            [InlineKeyboardButton(text="⬅️ ZURUECK", callback_data="friend:challenge:create")],
        ]
    )


def build_tournament_created_keyboard(
    *,
    invite_link: str,
    tournament_id: str,
    can_start: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="📤 Einladung teilen ->",
                url=build_tournament_share_url(
                    base_link=invite_link,
                    share_text="🏆 Tritt meinem Deutsch-Turnier bei!",
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Link kopieren",
                callback_data=f"friend:tournament:copy:{tournament_id}",
            )
        ],
    ]
    if can_start:
        rows.append(
            [
                InlineKeyboardButton(
                    text="▶️ Turnier starten",
                    callback_data=f"friend:tournament:start:{tournament_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="🔄 Aktualisieren", callback_data=f"friend:tournament:view:{tournament_id}")]
    )
    rows.append([InlineKeyboardButton(text="🏠 Menü", callback_data="home:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_tournament_lobby_keyboard(
    *,
    invite_code: str,
    tournament_id: str,
    can_join: bool,
    can_start: bool,
    play_challenge_id: str | None,
    show_share_result: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_join:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Beitreten",
                    callback_data=f"friend:tournament:join:{invite_code}",
                )
            ]
        )
    if can_start:
        rows.append(
            [
                InlineKeyboardButton(
                    text="▶️ Turnier starten",
                    callback_data=f"friend:tournament:start:{tournament_id}",
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
                    callback_data=f"friend:tournament:share:{tournament_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="🔄 Aktualisieren", callback_data=f"friend:tournament:view:{tournament_id}")]
    )
    rows.append([InlineKeyboardButton(text="🏠 Menü", callback_data="home:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_tournament_share_keyboard(*, share_url: str, tournament_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 JETZT TEILEN", url=share_url)],
            [
                InlineKeyboardButton(
                    text="🔄 Aktualisieren",
                    callback_data=f"friend:tournament:view:{tournament_id}",
                )
            ],
            [InlineKeyboardButton(text="🏠 Menü", callback_data="home:open")],
        ]
    )
