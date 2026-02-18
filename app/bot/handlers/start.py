from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.services.user_onboarding import UserOnboardingService

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    if message.from_user is None:
        await message.answer(TEXTS_DE["msg.system.error"])
        return

    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=message.from_user,
        )

    response_text = "\n".join(
        [
            TEXTS_DE["msg.home.title"],
            TEXTS_DE["msg.home.energy"].format(
                free_energy=snapshot.free_energy,
                paid_energy=snapshot.paid_energy,
            ),
            TEXTS_DE["msg.home.streak"].format(streak=snapshot.current_streak),
        ]
    )
    await message.answer(response_text, reply_markup=build_home_keyboard())
