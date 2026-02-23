from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ SPIELEN", callback_data="play")],
            [InlineKeyboardButton(text="🧠 ARTIKEL SPRINT", callback_data="mode:ARTIKEL_SPRINT")],
            [InlineKeyboardButton(text="🔥 DAILY CHALLENGE", callback_data="daily_challenge")],
            [
                InlineKeyboardButton(
                    text="👥 FREUNDE EINLADEN", callback_data="friend:challenge:create"
                )
            ],
            [InlineKeyboardButton(text="📚 CASES PRACTICE", callback_data="mode:CASES_PRACTICE")],
            [InlineKeyboardButton(text="🛒 SHOP", callback_data="shop:open")],
            [InlineKeyboardButton(text="🎁 REFERRAL BONUS", callback_data="referral:open")],
        ]
    )
