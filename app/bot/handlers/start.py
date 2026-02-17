from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.texts.de import TEXTS_DE

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(TEXTS_DE["msg.home.title"])
