from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import friend_challenge_share
from app.core.config import get_settings

build_friend_challenge_share_url = friend_challenge_share.build_friend_challenge_share_url
build_friend_challenge_share_keyboard = friend_challenge_share.build_friend_challenge_share_keyboard
build_friend_challenge_share_confirmed_keyboard = (
    friend_challenge_share.build_friend_challenge_share_confirmed_keyboard
)
build_friend_challenge_result_share_keyboard = (
    friend_challenge_share.build_friend_challenge_result_share_keyboard
)


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
                InlineKeyboardButton(
                    text="⚔️ Jetzt spielen",
                    callback_data=f"friend:next:{challenge_id}",
                )
            ],
        ]
    )


def build_friend_challenge_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
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
