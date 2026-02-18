from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Spielen", callback_data="play")],
            [InlineKeyboardButton(text="Daily Challenge", callback_data="daily_challenge")],
            [InlineKeyboardButton(text="Artikel Sprint", callback_data="mode:ARTIKEL_SPRINT")],
            [InlineKeyboardButton(text="Cases Practice", callback_data="mode:CASES_PRACTICE")],
            [InlineKeyboardButton(text="⚡ +10 Energie (10⭐)", callback_data="buy:ENERGY_10")],
            [InlineKeyboardButton(text="📦 Mega Pack (15⭐)", callback_data="buy:MEGA_PACK_15")],
        ]
    )
