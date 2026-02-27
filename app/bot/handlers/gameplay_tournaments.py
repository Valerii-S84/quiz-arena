from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.handlers import gameplay_callbacks, gameplay_helpers
from app.bot.handlers.gameplay_flows import tournament_flow, tournament_lobby_flow
from app.bot.handlers.gameplay_tournaments_more import (
    handle_tournament_copy_link,
    handle_tournament_share,
    handle_tournament_view,
)
from app.bot.texts.de import TEXTS_DE
from app.db.repo.users_repo import UsersRepo
from app.game.tournaments import TournamentServiceFacade
from app.game.tournaments.errors import (
    TournamentAccessError,
    TournamentAlreadyStartedError,
    TournamentClosedError,
    TournamentFullError,
    TournamentInsufficientParticipantsError,
    TournamentNotFoundError,
)


def _gameplay():
    from app.bot.handlers import gameplay

    return gameplay


def register(router: Router) -> None:
    router.callback_query(F.data.regexp(gameplay_callbacks.TOURNAMENT_FORMAT_RE))(
        handle_tournament_create_from_format
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.TOURNAMENT_JOIN_RE))(
        handle_tournament_join
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.TOURNAMENT_COPY_LINK_RE))(
        handle_tournament_copy_link
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.TOURNAMENT_START_RE))(
        handle_tournament_start
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.TOURNAMENT_VIEW_RE))(handle_tournament_view)
    router.callback_query(F.data.regexp(gameplay_callbacks.TOURNAMENT_SHARE_RE))(
        handle_tournament_share
    )


def _tournament_error_key(exc: Exception) -> str:
    if isinstance(exc, TournamentNotFoundError | TournamentAccessError):
        return "msg.tournament.not_found"
    if isinstance(exc, TournamentFullError):
        return "msg.tournament.full"
    if isinstance(exc, TournamentInsufficientParticipantsError):
        return "msg.tournament.start.need_two"
    if isinstance(exc, TournamentClosedError | TournamentAlreadyStartedError):
        return "msg.tournament.closed"
    return "msg.system.error"


async def handle_tournament_create_from_format(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    rounds = gameplay_callbacks.parse_tournament_format(callback.data)
    if rounds is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    gameplay = _gameplay()
    try:
        await tournament_flow.handle_tournament_create_from_format(
            callback,
            rounds=rounds,
            session_local=gameplay.SessionLocal,
            user_onboarding_service=gameplay.UserOnboardingService,
            tournament_service=TournamentServiceFacade,
            build_tournament_invite_link=gameplay_helpers._build_tournament_invite_link,
            emit_analytics_event=gameplay.emit_analytics_event,
            event_source_bot=gameplay.EVENT_SOURCE_BOT,
        )
    except Exception as exc:
        await callback.answer(TEXTS_DE[_tournament_error_key(exc)], show_alert=True)


async def handle_tournament_join(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    invite_code = gameplay_callbacks.parse_tournament_invite_code(callback.data)
    if invite_code is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    gameplay = _gameplay()
    try:
        await tournament_lobby_flow.handle_tournament_join_by_invite(
            callback,
            invite_code=invite_code,
            session_local=gameplay.SessionLocal,
            user_onboarding_service=gameplay.UserOnboardingService,
            tournament_service=TournamentServiceFacade,
            users_repo=UsersRepo,
            emit_analytics_event=gameplay.emit_analytics_event,
            event_source_bot=gameplay.EVENT_SOURCE_BOT,
        )
    except Exception as exc:
        await callback.answer(TEXTS_DE[_tournament_error_key(exc)], show_alert=True)


async def handle_tournament_start(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    tournament_id = gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.TOURNAMENT_START_RE,
        callback_data=callback.data,
    )
    if tournament_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    gameplay = _gameplay()
    try:
        await tournament_lobby_flow.handle_tournament_start(
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
        await callback.answer(TEXTS_DE[_tournament_error_key(exc)], show_alert=True)
