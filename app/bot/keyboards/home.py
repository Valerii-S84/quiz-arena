from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔥 Tägliche Challenge", callback_data="daily_challenge")],
            [InlineKeyboardButton(text="⚔️ Duell", callback_data="friend:challenge:create")],
            [InlineKeyboardButton(text="🎯 Schnell-Runde", callback_data="play")],
            [InlineKeyboardButton(text="📚 Artikel-Training", callback_data="mode:ARTIKEL_SPRINT")],
            [InlineKeyboardButton(text="🏪 Marktplatz", callback_data="shop:open")],
        ]
    )
