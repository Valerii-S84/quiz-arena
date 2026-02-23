from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.handlers import start_flow
from app.bot.handlers.start_helpers import (  # noqa: F401
    _notify_creator_about_join,
    _resolve_opponent_label,
)
from app.bot.handlers.start_parsing import (  # noqa: F401
    _extract_friend_challenge_token,
    _extract_start_payload,
)
from app.bot.handlers.start_views import (  # noqa: F401
    _build_friend_plan_text,
    _build_friend_score_text,
    _build_friend_ttl_text,
    _build_home_text,
    _build_question_text,
)
from app.db.session import SessionLocal  # noqa: F401
from app.economy.offers.service import OfferService  # noqa: F401
from app.game.sessions.service import GameSessionService  # noqa: F401
from app.services.user_onboarding import UserOnboardingService  # noqa: F401

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await start_flow.handle_start_message(message)


@router.callback_query(F.data == "shop:open")
async def handle_shop_open(callback: CallbackQuery) -> None:
    await start_flow.handle_shop_open(callback)


@router.callback_query(F.data == "home:open")
async def handle_home_open(callback: CallbackQuery) -> None:
    await start_flow.handle_home_open(callback)
