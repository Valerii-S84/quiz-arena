from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ MIX SPRINT", callback_data="play")],
            [InlineKeyboardButton(text="🧠 ARTIKEL SPRINT", callback_data="mode:ARTIKEL_SPRINT")],
            [InlineKeyboardButton(text="🥊 DUELL", callback_data="friend:challenge:create")],
            [InlineKeyboardButton(text="🛒 SHOP", callback_data="shop:open")],
        ]
    )
