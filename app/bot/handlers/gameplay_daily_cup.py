from __future__ import annotations

from functools import partial

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.handlers import gameplay_callbacks, gameplay_helpers
from app.bot.handlers.gameplay_flows import daily_cup_flow
from app.bot.keyboards.tournament import build_tournament_share_url
from app.bot.texts.de import TEXTS_DE
from app.db.repo.users_repo import UsersRepo
from app.game.tournaments import TournamentServiceFacade
from app.game.tournaments.errors import TournamentAccessError, TournamentClosedError, TournamentNotFoundError


def _gameplay():
    from app.bot.handlers import gameplay

    return gameplay


_build_daily_cup_share_result_url = partial(
    gameplay_helpers._build_tournament_share_url,
    build_share_url=build_tournament_share_url,
)


def register(router: Router) -> None:
    router.callback_query(F.data.regexp(gameplay_callbacks.DAILY_CUP_JOIN_RE))(handle_daily_cup_join)
    router.callback_query(F.data.regexp(gameplay_callbacks.DAILY_CUP_VIEW_RE))(handle_daily_cup_view)
    router.callback_query(F.data.regexp(gameplay_callbacks.DAILY_CUP_SHARE_RE))(handle_daily_cup_share)


def _daily_cup_error_key(exc: Exception) -> str:
    if isinstance(exc, TournamentNotFoundError | TournamentAccessError):
        return "msg.tournament.not_found"
    if isinstance(exc, TournamentClosedError):
        return "msg.daily_cup.closed"
    return "msg.system.error"


async def handle_daily_cup_join(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    tournament_id = gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.DAILY_CUP_JOIN_RE,
        callback_data=callback.data,
    )
    if tournament_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    gameplay = _gameplay()
    try:
        await daily_cup_flow.handle_daily_cup_join(
            callback,
            tournament_id=tournament_id,
            session_local=gameplay.SessionLocal,
            user_onboarding_service=gameplay.UserOnboardingService,
            tournament_service=TournamentServiceFacade,
            users_repo=UsersRepo,
            emit_analytics_event=gameplay.emit_analytics_event,
            event_source_bot=gameplay.EVENT_SOURCE_BOT,
        )
    except Exception as exc:
        await callback.answer(TEXTS_DE[_daily_cup_error_key(exc)], show_alert=True)


async def handle_daily_cup_view(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    tournament_id = gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.DAILY_CUP_VIEW_RE,
        callback_data=callback.data,
    )
    if tournament_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    gameplay = _gameplay()
    try:
        await daily_cup_flow.handle_daily_cup_view(
            callback,
            tournament_id=tournament_id,
            session_local=gameplay.SessionLocal,
            user_onboarding_service=gameplay.UserOnboardingService,
            tournament_service=TournamentServiceFacade,
            users_repo=UsersRepo,
            emit_analytics_event=gameplay.emit_analytics_event,
            event_source_bot=gameplay.EVENT_SOURCE_BOT,
        )
    except Exception as exc:
        await callback.answer(TEXTS_DE[_daily_cup_error_key(exc)], show_alert=True)


async def handle_daily_cup_share(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    tournament_id = gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.DAILY_CUP_SHARE_RE,
        callback_data=callback.data,
    )
    if tournament_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    gameplay = _gameplay()
    try:
        await daily_cup_flow.handle_daily_cup_share_result(
            callback,
            tournament_id=tournament_id,
            session_local=gameplay.SessionLocal,
            user_onboarding_service=gameplay.UserOnboardingService,
            tournament_service=TournamentServiceFacade,
            build_tournament_share_result_url=_build_daily_cup_share_result_url,
            emit_analytics_event=gameplay.emit_analytics_event,
            event_source_bot=gameplay.EVENT_SOURCE_BOT,
        )
    except Exception as exc:
        await callback.answer(TEXTS_DE[_daily_cup_error_key(exc)], show_alert=True)
