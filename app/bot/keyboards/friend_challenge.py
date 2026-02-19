from urllib.parse import quote_plus

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _build_share_url(*, invite_link: str, share_text: str) -> str:
    return (
        "https://t.me/share/url"
        f"?url={quote_plus(invite_link)}"
        f"&text={quote_plus(share_text)}"
    )


def build_friend_challenge_next_keyboard(*, challenge_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ NAECHSTE RUNDE", callback_data=f"friend:next:{challenge_id}")],
            [InlineKeyboardButton(text="⬅️ ZURUECK", callback_data="home:open")],
        ]
    )


def build_friend_challenge_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ ZURUECK", callback_data="home:open")],
        ]
    )


def build_friend_challenge_share_keyboard(
    *,
    invite_link: str | None,
    challenge_id: str | None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if invite_link:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Link teilen",
                    url=_build_share_url(
                        invite_link=invite_link,
                        share_text="Quiz Arena: Spiele ein Duell mit mir!",
                    ),
                )
            ]
        )
    if challenge_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text="▶️ DUELL STARTEN",
                    callback_data=f"friend:next:{challenge_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ ZURUECK", callback_data="home:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_friend_challenge_limit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎟 1 DUELL  |  5⭐", callback_data="buy:FRIEND_CHALLENGE_5")],
            [InlineKeyboardButton(text="💎 PREMIUM STARTER", callback_data="buy:PREMIUM_STARTER")],
            [InlineKeyboardButton(text="⬅️ ZURUECK", callback_data="home:open")],
        ]
    )
