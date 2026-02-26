from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_daily_result_keyboard(*, daily_run_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Nochmal anschauen",
                    callback_data=f"daily:result:{daily_run_id}",
                ),
                InlineKeyboardButton(text="Zum Menü", callback_data="home:open"),
            ]
        ]
    )


def build_daily_push_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Jetzt spielen →", callback_data="daily_challenge")]
        ]
    )
