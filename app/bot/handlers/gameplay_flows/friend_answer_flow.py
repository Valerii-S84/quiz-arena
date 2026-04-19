from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.handlers.gameplay_flows import friend_answer_flow_runtime
from app.bot.handlers.gameplay_flows.friend_answer_completion_flow import (
    handle_completed_friend_challenge,
)
from app.bot.handlers.gameplay_flows.friend_challenge_push_quota import reserve_duel_push_slot
from app.bot.texts.de import TEXTS_DE
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.sessions.types import AnswerSessionResult


@dataclass(slots=True)
class _FriendAnswerRequest:
    message: Message
    telegram_user: TelegramUser


@dataclass(slots=True)
class _FriendAnswerDeps:
    session_local: Any
    user_onboarding_service: Any
    game_session_service: Any
    resolve_opponent_label: Any
    notify_opponent: Any
    friend_opponent_user_id: Any
    build_friend_score_text: Any
    build_friend_ttl_text: Any
    build_friend_finish_text: Any
    build_public_badge_label: Any
    build_friend_proof_card_text: Any
    enqueue_friend_challenge_proof_cards: Any
    build_series_progress_text: Any
    send_friend_round_question: Any


def _build_friend_answer_deps(
    *,
    session_local,
    user_onboarding_service,
    game_session_service,
    resolve_opponent_label,
    notify_opponent,
    friend_opponent_user_id,
    build_friend_score_text,
    build_friend_ttl_text,
    build_friend_finish_text,
    build_public_badge_label,
    build_friend_proof_card_text,
    enqueue_friend_challenge_proof_cards,
    build_series_progress_text,
    send_friend_round_question,
) -> _FriendAnswerDeps:
    return _FriendAnswerDeps(
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        game_session_service=game_session_service,
        resolve_opponent_label=resolve_opponent_label,
        notify_opponent=notify_opponent,
        friend_opponent_user_id=friend_opponent_user_id,
        build_friend_score_text=build_friend_score_text,
        build_friend_ttl_text=build_friend_ttl_text,
        build_friend_finish_text=build_friend_finish_text,
        build_public_badge_label=build_public_badge_label,
        build_friend_proof_card_text=build_friend_proof_card_text,
        enqueue_friend_challenge_proof_cards=enqueue_friend_challenge_proof_cards,
        build_series_progress_text=build_series_progress_text,
        send_friend_round_question=send_friend_round_question,
    )


async def _parse_friend_answer_request(
    callback: CallbackQuery,
) -> _FriendAnswerRequest | None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return None

    return _FriendAnswerRequest(
        message=cast(Message, callback.message),
        telegram_user=callback.from_user,
    )


async def _run_friend_answer_branch(
    callback: CallbackQuery,
    *,
    request: _FriendAnswerRequest,
    result: AnswerSessionResult,
    now_utc: datetime,
    deps: _FriendAnswerDeps,
) -> None:
    await friend_answer_flow_runtime.run_friend_answer_branch(
        callback,
        message=request.message,
        telegram_user=request.telegram_user,
        result=result,
        now_utc=now_utc,
        deps=deps,
        friend_challenges_repo=FriendChallengesRepo,
        reserve_duel_push_slot=reserve_duel_push_slot,
        handle_completed_friend_challenge=handle_completed_friend_challenge,
    )


async def handle_friend_answer_branch(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    now_utc: datetime,
    session_local,
    user_onboarding_service,
    game_session_service,
    resolve_opponent_label,
    notify_opponent,
    friend_opponent_user_id,
    build_friend_score_text,
    build_friend_ttl_text,
    build_friend_finish_text,
    build_public_badge_label,
    build_friend_proof_card_text,
    enqueue_friend_challenge_proof_cards,
    build_series_progress_text,
    send_friend_round_question,
) -> None:
    request = await _parse_friend_answer_request(callback)
    if request is None:
        return

    await _run_friend_answer_branch(
        callback,
        request=request,
        result=result,
        now_utc=now_utc,
        deps=_build_friend_answer_deps(
            session_local=session_local,
            user_onboarding_service=user_onboarding_service,
            game_session_service=game_session_service,
            resolve_opponent_label=resolve_opponent_label,
            notify_opponent=notify_opponent,
            friend_opponent_user_id=friend_opponent_user_id,
            build_friend_score_text=build_friend_score_text,
            build_friend_ttl_text=build_friend_ttl_text,
            build_friend_finish_text=build_friend_finish_text,
            build_public_badge_label=build_public_badge_label,
            build_friend_proof_card_text=build_friend_proof_card_text,
            enqueue_friend_challenge_proof_cards=enqueue_friend_challenge_proof_cards,
            build_series_progress_text=build_series_progress_text,
            send_friend_round_question=send_friend_round_question,
        ),
    )
