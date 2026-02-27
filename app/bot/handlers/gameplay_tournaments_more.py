from __future__ import annotations

from functools import partial

from aiogram.types import CallbackQuery

from app.bot.handlers import gameplay_callbacks, gameplay_helpers
from app.bot.handlers.gameplay_flows import tournament_flow, tournament_lobby_flow
from app.bot.keyboards.tournament import build_tournament_share_url
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


_build_tournament_share_result_url = partial(
    gameplay_helpers._build_tournament_share_url,
    build_share_url=build_tournament_share_url,
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


async def handle_tournament_copy_link(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    tournament_id = gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.TOURNAMENT_COPY_LINK_RE,
        callback_data=callback.data,
    )
    if tournament_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    gameplay = _gameplay()
    try:
        await tournament_lobby_flow.handle_tournament_copy_link(
            callback,
            tournament_id=tournament_id,
            session_local=gameplay.SessionLocal,
            user_onboarding_service=gameplay.UserOnboardingService,
            tournament_service=TournamentServiceFacade,
            build_tournament_invite_link=gameplay_helpers._build_tournament_invite_link,
        )
    except Exception as exc:
        await callback.answer(TEXTS_DE[_tournament_error_key(exc)], show_alert=True)


async def handle_tournament_view(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    tournament_id = gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.TOURNAMENT_VIEW_RE,
        callback_data=callback.data,
    )
    if tournament_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    gameplay = _gameplay()
    try:
        await tournament_lobby_flow.handle_tournament_view(
            callback,
            tournament_id=tournament_id,
            session_local=gameplay.SessionLocal,
            user_onboarding_service=gameplay.UserOnboardingService,
            tournament_service=TournamentServiceFacade,
            users_repo=UsersRepo,
        )
    except Exception as exc:
        await callback.answer(TEXTS_DE[_tournament_error_key(exc)], show_alert=True)


async def handle_tournament_share(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    tournament_id = gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.TOURNAMENT_SHARE_RE,
        callback_data=callback.data,
    )
    if tournament_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    gameplay = _gameplay()
    try:
        await tournament_flow.handle_tournament_share_result(
            callback,
            tournament_id=tournament_id,
            session_local=gameplay.SessionLocal,
            user_onboarding_service=gameplay.UserOnboardingService,
            tournament_service=TournamentServiceFacade,
            build_tournament_share_result_url=_build_tournament_share_result_url,
            emit_analytics_event=gameplay.emit_analytics_event,
            event_source_bot=gameplay.EVENT_SOURCE_BOT,
        )
    except Exception as exc:
        await callback.answer(TEXTS_DE[_tournament_error_key(exc)], show_alert=True)
