from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery, Message

from app.bot.handlers.start_friend_challenge_flow import handle_start_friend_challenge_payload
from app.bot.handlers.start_helpers import (
    _notify_creator_about_join,
    _resolve_opponent_label,
    _send_home_message,
)
from app.bot.handlers.start_parsing import (
    _extract_duel_challenge_id,
    _extract_friend_challenge_token,
    _extract_start_payload,
    _extract_tournament_invite_code,
)
from app.bot.handlers.start_tournament_flow import handle_start_tournament_payload
from app.bot.handlers.start_views import (
    _build_friend_plan_text,
    _build_friend_score_text,
    _build_friend_ttl_text,
    _build_home_text,
    _build_question_text,
)
from app.bot.keyboards.offers import build_offer_keyboard
from app.bot.keyboards.shop import build_shop_keyboard
from app.bot.texts.de import TEXTS_DE
from app.core.config import get_settings
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.offers.service import OfferLoggingError, OfferService
from app.game import TournamentServiceFacade
from app.game.sessions.service import GameSessionService
from app.services.channel_bonus import ChannelBonusService
from app.services.user_onboarding import UserOnboardingService


async def handle_start_message(message: Message) -> None:
    if message.from_user is None:
        await message.answer(TEXTS_DE["msg.system.error"])
        return

    now_utc = datetime.now(timezone.utc)
    offer_selection = None
    friend_challenge_result = None
    start_payload = _extract_start_payload(message.text)
    friend_invite_token = _extract_friend_challenge_token(start_payload)
    duel_challenge_id = _extract_duel_challenge_id(start_payload)
    tournament_invite_code = _extract_tournament_invite_code(start_payload)

    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=message.from_user,
            start_payload=start_payload,
        )

        friend_challenge_result = await handle_start_friend_challenge_payload(
            session=session,
            now_utc=now_utc,
            snapshot=snapshot,
            friend_invite_token=friend_invite_token,
            duel_challenge_id=duel_challenge_id,
            start_message_id=message.message_id,
            game_session_service=GameSessionService,
            resolve_opponent_label=_resolve_opponent_label,
            build_friend_plan_text=_build_friend_plan_text,
            build_friend_score_text=_build_friend_score_text,
            build_friend_ttl_text=_build_friend_ttl_text,
            build_question_text=_build_question_text,
        )
        if friend_challenge_result is not None:
            pass
        else:
            handled_tournament = await handle_start_tournament_payload(
                message,
                session=session,
                tournament_invite_code=tournament_invite_code,
                viewer_user_id=snapshot.user_id,
                tournament_service=TournamentServiceFacade,
                users_repo=UsersRepo,
            )
            if handled_tournament:
                return

            try:
                offer_selection = await OfferService.evaluate_and_log_offer(
                    session,
                    user_id=snapshot.user_id,
                    idempotency_key=f"offer:start:{message.from_user.id}:{message.message_id}",
                    now_utc=now_utc,
                )
            except OfferLoggingError:
                offer_selection = None

    if friend_challenge_result is not None:
        if (
            friend_challenge_result.notify_creator
            and friend_challenge_result.notify_challenge is not None
            and friend_challenge_result.notify_joiner_user_id is not None
        ):
            await _notify_creator_about_join(
                message,
                challenge=friend_challenge_result.notify_challenge,
                joiner_user_id=friend_challenge_result.notify_joiner_user_id,
            )
        for outgoing_message in friend_challenge_result.messages:
            await message.answer(
                outgoing_message.text,
                reply_markup=outgoing_message.reply_markup,
                parse_mode=outgoing_message.parse_mode,
            )
        return

    response_text = _build_home_text(
        free_energy=snapshot.free_energy,
        paid_energy=snapshot.paid_energy,
        current_streak=snapshot.current_streak,
    )
    await _send_home_message(
        message,
        text=response_text,
        home_header_file_id=get_settings().telegram_home_header_file_id.strip(),
    )
    if offer_selection is not None:
        await message.answer(
            TEXTS_DE[offer_selection.text_key],
            reply_markup=build_offer_keyboard(offer_selection),
        )


async def handle_shop_open(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        channel_bonus_claimed = await ChannelBonusService.is_bonus_claimed(
            session, user_id=snapshot.user_id
        )

    await callback.message.answer(
        TEXTS_DE["msg.shop.title"],
        reply_markup=build_shop_keyboard(channel_bonus_claimed=channel_bonus_claimed),
    )
    await callback.answer()


async def handle_home_open(callback: CallbackQuery) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

    response_text = _build_home_text(
        free_energy=snapshot.free_energy,
        paid_energy=snapshot.paid_energy,
        current_streak=snapshot.current_streak,
    )
    await _send_home_message(
        callback.message,
        text=response_text,
        home_header_file_id=get_settings().telegram_home_header_file_id.strip(),
    )
    await callback.answer()
