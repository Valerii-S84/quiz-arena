from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_shop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ +10 Energie (10⭐)", callback_data="buy:ENERGY_10")],
            [InlineKeyboardButton(text="📦 Mega Pack (15⭐)", callback_data="buy:MEGA_PACK_15")],
            [InlineKeyboardButton(text="💎 Premium Starter (29⭐)", callback_data="buy:PREMIUM_STARTER")],
            [InlineKeyboardButton(text="💎 Premium Month (99⭐)", callback_data="buy:PREMIUM_MONTH")],
            [InlineKeyboardButton(text="💎 Premium Season (249⭐)", callback_data="buy:PREMIUM_SEASON")],
            [InlineKeyboardButton(text="💎 Premium Year (499⭐)", callback_data="buy:PREMIUM_YEAR")],
            [InlineKeyboardButton(text="🎟 Promo-Code", callback_data="promo:open")],
            [InlineKeyboardButton(text="⬅ Zurück", callback_data="home:open")],
        ]
    )
