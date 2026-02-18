from __future__ import annotations

from urllib.parse import quote_plus

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _build_share_url(*, invite_link: str, share_text: str) -> str:
    return (
        "https://t.me/share/url"
        f"?url={quote_plus(invite_link)}"
        f"&text={quote_plus(share_text)}"
    )


def build_referral_keyboard(
    *,
    invite_link: str | None,
    has_claimable_reward: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if invite_link:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Link teilen",
                    url=_build_share_url(
                        invite_link=invite_link,
                        share_text="Quiz Arena: Spiele mit mir!",
                    ),
                )
            ]
        )

    if has_claimable_reward:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Mega Pack",
                    callback_data="referral:reward:MEGA_PACK_15",
                ),
                InlineKeyboardButton(
                    text="Premium Starter",
                    callback_data="referral:reward:PREMIUM_STARTER",
                ),
            ]
        )

    rows.append([InlineKeyboardButton(text="Aktualisieren", callback_data="referral:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
