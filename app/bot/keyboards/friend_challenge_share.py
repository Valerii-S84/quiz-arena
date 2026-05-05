from __future__ import annotations

from urllib.parse import quote_plus

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.proof_card_share import (
    build_friend_challenge_inline_share_query,
    build_friend_challenge_invite_inline_share_query,
)
from app.game.duels import rollout as duel_rollout


def _build_share_url(*, invite_link: str, share_text: str) -> str:
    return (
        "https://t.me/share/url" f"?url={quote_plus(invite_link)}" f"&text={quote_plus(share_text)}"
    )


def build_friend_challenge_share_url(*, base_link: str, share_text: str) -> str:
    return _build_share_url(invite_link=base_link, share_text=share_text)


def build_friend_challenge_share_keyboard(
    *,
    invite_link: str | None,
    challenge_id: str | None,
) -> InlineKeyboardMarkup:
    if not invite_link or not challenge_id:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
            ]
        )
    rows = [
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
                text="✅ Einladung gesendet",
                callback_data=f"friend:invite:sent:{challenge_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="⚔️ Jetzt spielen",
                callback_data=f"friend:invite:required:{challenge_id}",
            )
        ],
    ]
    rows.append([InlineKeyboardButton(text="⏳ Auf Freund warten", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_friend_challenge_share_confirmed_keyboard(*, challenge_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
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
                    text="✅ Einladung gesendet",
                    callback_data=f"friend:invite:sent:{challenge_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚔️ Jetzt spielen",
                    callback_data=f"friend:next:{challenge_id}",
                )
            ],
            [InlineKeyboardButton(text="⏳ Auf Freund warten", callback_data="menu:main")],
        ]
    )


def build_friend_challenge_result_share_keyboard(
    *, share_url: str, challenge_id: str
) -> InlineKeyboardMarkup:
    del share_url
    rows = [
        [
            InlineKeyboardButton(
                text="📤 KARTE TEILEN",
                switch_inline_query=build_friend_challenge_inline_share_query(
                    challenge_id=challenge_id
                ),
            )
        ]
    ]
    if duel_rollout.is_canonical_duels_enabled():
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔁 REVANCHE",
                    callback_data=f"friend:rematch:{challenge_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
