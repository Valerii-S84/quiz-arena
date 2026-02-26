from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_referral_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Link teilen",
                    callback_data="referral:prompt:share",
                ),
                InlineKeyboardButton(
                    text="Spaeter",
                    callback_data="referral:prompt:later",
                ),
            ]
        ]
    )
