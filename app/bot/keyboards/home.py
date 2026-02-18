from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Spielen", callback_data="play")],
            [InlineKeyboardButton(text="Artikel Sprint", callback_data="mode:ARTIKEL_SPRINT")],
            [InlineKeyboardButton(text="Daily Challenge", callback_data="daily_challenge")],
            [InlineKeyboardButton(text="Cases Practice", callback_data="mode:CASES_PRACTICE")],
            [InlineKeyboardButton(text="🛒 Shop", callback_data="shop:open")],
            [InlineKeyboardButton(text="👥 Freunde einladen", callback_data="referral:open")],
            [InlineKeyboardButton(text="🎟 Promo", callback_data="promo:open")],
        ]
    )
