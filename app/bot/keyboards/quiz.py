from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_quiz_keyboard(
    *, session_id: str, options: tuple[str, str, str, str]
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"1. {options[0]}", callback_data=f"answer:{session_id}:0")],
            [InlineKeyboardButton(text=f"2. {options[1]}", callback_data=f"answer:{session_id}:1")],
            [InlineKeyboardButton(text=f"3. {options[2]}", callback_data=f"answer:{session_id}:2")],
            [InlineKeyboardButton(text=f"4. {options[3]}", callback_data=f"answer:{session_id}:3")],
            [InlineKeyboardButton(text="Stoppen und Menü", callback_data="game:stop")],
        ]
    )
