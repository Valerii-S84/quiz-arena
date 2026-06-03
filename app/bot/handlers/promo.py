from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.handlers.promo_input import (
    PROMO_MENU_MESSAGE_ID_KEY,
    PROMO_MENU_NONCE_KEY,
    PromoCode,
    issue_promo_menu_nonce,
    promo_waiting_is_expired,
    remember_promo_menu_message_id,
)
from app.bot.handlers.promo_prompt import prompt_for_promo_input as _prompt_for_promo_input
from app.bot.handlers.promo_redeem import redeem_promo_from_text as _redeem_promo_from_text
from app.bot.keyboards.shop import build_shop_keyboard
from app.bot.promo_callbacks import extract_promo_open_nonce
from app.bot.texts.de import TEXTS_DE
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal

router = Router(name="promo")
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("promo:open"))
async def handle_promo_open(callback: CallbackQuery, state: FSMContext | None = None) -> None:
    _log_promo_trigger(callback)
    if not await _is_valid_promo_source(callback, state):
        logger.warning(
            "INVALID_PROMO_SOURCE user=%s message_id=%s data=%s",
            _callback_user_id(callback),
            _callback_message_id(callback),
            callback.data,
        )
        await callback.answer()
        return
    if await is_user_in_quiz(callback):
        logger.warning("BLOCKED_PROMO_DURING_QUIZ user=%s", _callback_user_id(callback))
        await callback.answer()
        return
    if isinstance(callback.message, Message):
        await _prompt_for_promo_input(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "promo:cancel")
async def handle_promo_cancel(callback: CallbackQuery, state: FSMContext | None = None) -> None:
    if state is not None:
        await state.clear()
    if isinstance(callback.message, Message):
        promo_nonce = await issue_promo_menu_nonce(state)
        sent_message = await callback.message.answer(
            TEXTS_DE["msg.promo.cancelled"],
            reply_markup=build_shop_keyboard(promo_nonce=promo_nonce),
        )
        await remember_promo_menu_message_id(state, sent_message)
    await callback.answer()


@router.message(Command("promo"))
async def handle_promo_command(message: Message, state: FSMContext | None = None) -> None:
    if await is_user_in_quiz(message):
        logger.warning("BLOCKED_PROMO_DURING_QUIZ user=%s", _event_user_id(message))
        return
    await _redeem_promo_from_text(message, state=state)


@router.message(StateFilter(PromoCode.waiting_for_code), Command("cancel"))
async def handle_promo_cancel_command(
    message: Message,
    state: FSMContext | None = None,
) -> None:
    if state is not None:
        await state.clear()
    promo_nonce = await issue_promo_menu_nonce(state)
    sent_message = await message.answer(
        TEXTS_DE["msg.promo.cancelled"],
        reply_markup=build_shop_keyboard(promo_nonce=promo_nonce),
    )
    await remember_promo_menu_message_id(state, sent_message)


@router.message(StateFilter(PromoCode.waiting_for_code), F.text.startswith("/"))
async def handle_promo_waiting_command_passthrough(
    message: Message,
    state: FSMContext | None = None,
) -> None:
    if state is not None:
        await state.clear()
    raise SkipHandler()


@router.message(StateFilter(PromoCode.waiting_for_code), F.text)
async def handle_promo_code_input(message: Message, state: FSMContext | None = None) -> None:
    if state is not None and await promo_waiting_is_expired(state):
        await state.clear()
        return
    await _redeem_promo_from_text(
        message,
        state=state,
        allow_plain_text=True,
        from_waiting_state=True,
    )


async def is_user_in_quiz(event: CallbackQuery | Message) -> bool:
    telegram_user_id = _event_user_id(event)
    if telegram_user_id is None:
        return False
    async with SessionLocal.begin() as session:
        user = await UsersRepo.get_by_telegram_user_id(session, telegram_user_id)
        if user is None:
            return False
        stmt = (
            select(QuizSession.id)
            .where(QuizSession.user_id == user.id, QuizSession.status == "STARTED")
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None


def _log_promo_trigger(callback: CallbackQuery) -> None:
    logger.warning(
        "PROMO_TRIGGER user=%s chat=%s data=%s message_id=%s text=%r",
        _callback_user_id(callback),
        _callback_chat_id(callback),
        callback.data,
        _callback_message_id(callback),
        getattr(callback.message, "text", None),
    )


async def _is_valid_promo_source(
    callback: CallbackQuery,
    state: FSMContext | None,
) -> bool:
    if state is None:
        return False
    nonce = extract_promo_open_nonce(callback.data)
    if nonce is None:
        return False
    state_data = await state.get_data()
    if state_data.get(PROMO_MENU_NONCE_KEY) != nonce:
        return False
    expected_message_id = _coerce_message_id(state_data.get(PROMO_MENU_MESSAGE_ID_KEY))
    return expected_message_id is None or _callback_message_id(callback) == expected_message_id


def _callback_user_id(callback: CallbackQuery) -> int | None:
    return _event_user_id(callback)


def _callback_chat_id(callback: CallbackQuery) -> int | None:
    chat = getattr(callback.message, "chat", None)
    return _coerce_message_id(getattr(chat, "id", None))


def _callback_message_id(callback: CallbackQuery) -> int | None:
    return _coerce_message_id(getattr(callback.message, "message_id", None))


def _event_user_id(event: CallbackQuery | Message) -> int | None:
    return _coerce_message_id(getattr(event.from_user, "id", None))


def _coerce_message_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None
