from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.promo_input import PromoCode
from app.bot.handlers.promo_prompt import prompt_for_promo_input as _prompt_for_promo_input
from app.bot.handlers.promo_redeem import redeem_promo_from_text as _redeem_promo_from_text
from app.bot.keyboards.shop import build_shop_keyboard
from app.bot.texts.de import TEXTS_DE

router = Router(name="promo")


@router.callback_query(F.data == "promo:open")
async def handle_promo_open(callback: CallbackQuery, state: FSMContext | None = None) -> None:
    if isinstance(callback.message, Message):
        await _prompt_for_promo_input(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "promo:cancel")
async def handle_promo_cancel(callback: CallbackQuery, state: FSMContext | None = None) -> None:
    if state is not None:
        await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            TEXTS_DE["msg.promo.cancelled"],
            reply_markup=build_shop_keyboard(),
        )
    await callback.answer()


@router.message(Command("promo"))
async def handle_promo_command(message: Message, state: FSMContext | None = None) -> None:
    await _redeem_promo_from_text(message, state=state)


@router.message(StateFilter(PromoCode.waiting_for_code), Command("cancel"))
async def handle_promo_cancel_command(
    message: Message,
    state: FSMContext | None = None,
) -> None:
    if state is not None:
        await state.clear()
    await message.answer(TEXTS_DE["msg.promo.cancelled"], reply_markup=build_shop_keyboard())


@router.message(StateFilter(PromoCode.waiting_for_code), F.text)
async def handle_promo_code_input(message: Message, state: FSMContext | None = None) -> None:
    await _redeem_promo_from_text(
        message,
        state=state,
        allow_plain_text=True,
        from_waiting_state=True,
    )
