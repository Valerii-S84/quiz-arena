from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_quiz_keyboard(
    *,
    session_id: str,
    options: tuple[str, str, str, str],
    is_tournament: bool = False,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=options[0], callback_data=f"answer:{session_id}:0")],
        [InlineKeyboardButton(text=options[1], callback_data=f"answer:{session_id}:1")],
        [InlineKeyboardButton(text=options[2], callback_data=f"answer:{session_id}:2")],
        [InlineKeyboardButton(text=options[3], callback_data=f"answer:{session_id}:3")],
    ]
    if not is_tournament:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Stoppen und Menü",
                    callback_data=f"game:stop:{session_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
