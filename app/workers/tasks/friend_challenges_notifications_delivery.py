from __future__ import annotations


async def send_message_safely(*, bot, chat_id: int | None, text: str, reply_markup=None) -> bool:
    if chat_id is None:
        return False
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        return True
    except Exception:
        return False
