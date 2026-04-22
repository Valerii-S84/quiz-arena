from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_shop_keyboard(*, channel_bonus_claimed: bool = False) -> InlineKeyboardMarkup:
    channel_bonus_row = [
        InlineKeyboardButton(
            text="✅ Kanal-Bonus bereits erhalten",
            callback_data="channel_bonus:claimed",
        )
    ]
    if not channel_bonus_claimed:
        channel_bonus_row = [
            InlineKeyboardButton(
                text="📺 Kanal abonnieren → volle Energie",
                callback_data="channel_bonus:open",
            )
        ]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Energie +10 | 5⭐", callback_data="buy:ENERGY_10")],
            [
                InlineKeyboardButton(
                    text="⚔️ Duell-Ticket | 5⭐",
                    callback_data="buy:FRIEND_CHALLENGE_5",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 Premium Starter | 29⭐",
                    callback_data="buy:PREMIUM_STARTER",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 Premium Monat | 99⭐", callback_data="buy:PREMIUM_MONTH"
                )
            ],
            channel_bonus_row,
            [
                InlineKeyboardButton(
                    text="👥 Freunde einladen → Belohnung",
                    callback_data="referral:open",
                )
            ],
            [InlineKeyboardButton(text="🎟️ Promo-Code eingeben", callback_data="promo:open")],
            [InlineKeyboardButton(text="⬅️ Zurück", callback_data="home:open")],
        ]
    )
