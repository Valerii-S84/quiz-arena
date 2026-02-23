from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_shop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ ENERGIE +10  |  5⭐", callback_data="buy:ENERGY_10")],
            [
                InlineKeyboardButton(
                    text="🤝 DUELL TICKET  |  5⭐",
                    callback_data="buy:FRIEND_CHALLENGE_5",
                )
            ],
            [InlineKeyboardButton(text="📦 MEGA PACK  |  15⭐", callback_data="buy:MEGA_PACK_15")],
            [
                InlineKeyboardButton(
                    text="💎 PREMIUM STARTER  |  29⭐",
                    callback_data="buy:PREMIUM_STARTER",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 PREMIUM MONTH  |  99⭐", callback_data="buy:PREMIUM_MONTH"
                )
            ],
            [InlineKeyboardButton(text="🎟 PROMO-CODE", callback_data="promo:open")],
            [InlineKeyboardButton(text="⬅️ ZURÜCK", callback_data="home:open")],
        ]
    )
