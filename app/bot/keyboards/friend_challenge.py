from urllib.parse import quote_plus

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.proof_card_share import (
    build_friend_challenge_inline_share_query,
    build_friend_challenge_invite_inline_share_query,
)
from app.core.config import get_settings


def _build_share_url(*, invite_link: str, share_text: str) -> str:
    return (
        "https://t.me/share/url" f"?url={quote_plus(invite_link)}" f"&text={quote_plus(share_text)}"
    )


def build_friend_challenge_share_url(*, base_link: str, share_text: str) -> str:
    return _build_share_url(invite_link=base_link, share_text=share_text)


def build_friend_challenge_create_keyboard() -> InlineKeyboardMarkup:
    settings = get_settings()
    rows = [
        [
            InlineKeyboardButton(
                text="👤 Freund herausfordern",
                callback_data="friend:challenge:type:direct",
            )
        ],
    ]
    if settings.tournament_friends_enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🏆 Turnier mit Freunden",
                    callback_data="friend:challenge:type:tournament",
                )
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton(text="🥊 Arena Cup", callback_data="daily:cup:menu")],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_friend_challenge_format_keyboard(*, challenge_type: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ Blitz – 5 Fragen",
                    callback_data=f"friend:challenge:format:{challenge_type}:5",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧠 Voll – 12 Fragen",
                    callback_data=f"friend:challenge:format:{challenge_type}:12",
                )
            ],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="friend:challenge:create")],
        ]
    )


def build_friend_challenge_next_keyboard(*, challenge_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ NAECHSTE RUNDE", callback_data=f"friend:next:{challenge_id}"
                )
            ],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
        ]
    )


def build_friend_challenge_start_keyboard(*, challenge_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚔️ Jetzt spielen", callback_data=f"friend:challenge:round:start:{challenge_id}")
            ],
        ]
    )


def build_friend_challenge_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
        ]
    )


def build_friend_challenge_share_keyboard(
    *,
    invite_link: str | None,
    challenge_id: str | None,
    total_rounds: int = 12,
) -> InlineKeyboardMarkup:
    del total_rounds
    if not invite_link or not challenge_id:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⚔️ Meine Duelle", callback_data="friend:my:duels")],
                [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ Herausforderung annehmen",
                    url=invite_link,
                )
            ],
            [
                InlineKeyboardButton(
                    text="📤 Teilen ->",
                    switch_inline_query=build_friend_challenge_invite_inline_share_query(
                        challenge_id=challenge_id
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Link kopieren",
                    callback_data=f"friend:copy:{challenge_id}",
                )
            ],
            [InlineKeyboardButton(text="⚔️ Meine Duelle", callback_data="friend:my:duels")],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
        ]
    )


def build_friend_challenge_waiting_keyboard(*, challenge_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            build_friend_challenge_start_keyboard(challenge_id=challenge_id).inline_keyboard[0],
            [
                InlineKeyboardButton(
                    text="⏳ Auf Freund warten",
                    callback_data=f"friend:challenge:waiting:{challenge_id}",
                )
            ],
            [InlineKeyboardButton(text="🏠 Hauptmenü", callback_data="menu:main")],
        ]
    )


def build_friend_challenge_finished_keyboard(
    *,
    challenge_id: str,
    share_url: str | None = None,
    include_share: bool = True,
    show_best_of_three: bool = True,
    show_next_series_game: bool = False,
) -> InlineKeyboardMarkup:
    del share_url, show_best_of_three, show_next_series_game
    rows: list[list[InlineKeyboardButton]] = []
    if include_share:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📤 Ergebnis teilen",
                    callback_data=f"friend:share:result:{challenge_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="🔄 Revanche", callback_data=f"friend:rematch:{challenge_id}")]
    )
    rows.append([InlineKeyboardButton(text="🏠 Menü", callback_data="home:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_friend_challenge_result_share_keyboard(*, share_url: str, challenge_id: str) -> InlineKeyboardMarkup:
    del share_url
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 KARTE TEILEN",
                    switch_inline_query=build_friend_challenge_inline_share_query(
                        challenge_id=challenge_id
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔁 REVANCHE", callback_data=f"friend:rematch:{challenge_id}"
                )
            ],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
        ]
    )


def build_friend_challenge_limit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎟 1 DUELL  |  5⭐", callback_data="buy:FRIEND_CHALLENGE_5"
                )
            ],
            [InlineKeyboardButton(text="💎 PREMIUM STARTER", callback_data="buy:PREMIUM_STARTER")],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
        ]
    )


def build_friend_open_taken_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌍 Neue offene Herausforderung",
                    callback_data="friend:challenge:type:open",
                )
            ],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
        ]
    )


def build_friend_pending_expired_keyboard(*, challenge_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌍 Als offene Herausforderung posten",
                    callback_data=f"friend:open:repost:{challenge_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Löschen",
                    callback_data=f"friend:delete:{challenge_id}",
                )
            ],
        ]
    )
