from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.handlers.gameplay_flows.friend_answer_completion_flow import (
    FriendCompletionCallbacks,
    handle_completed_friend_challenge,
)
from app.bot.handlers.gameplay_flows.friend_challenge_push_quota import reserve_duel_push_slot
from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_finished_keyboard,
    build_friend_challenge_start_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.types import (
    AnswerSessionResult,
    FriendChallengeRoundStartResult,
    FriendChallengeSnapshot,
)
from app.services.user_onboarding import HomeSnapshot


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


@dataclass(slots=True)
class _FriendAnswerContext:
    snapshot: HomeSnapshot
    challenge: FriendChallengeSnapshot
    opponent_label: str
    opponent_user_id: int | None


@dataclass(slots=True)
class _StartedFriendRoundPayload:
    snapshot: HomeSnapshot
    round_start: FriendChallengeRoundStartResult


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


async def _ensure_home_snapshot(
    session,
    *,
    user_onboarding_service,
    telegram_user: TelegramUser,
) -> HomeSnapshot:
    return await user_onboarding_service.ensure_home_snapshot(
        session,
        telegram_user=telegram_user,
    )


async def _load_home_snapshot(
    *,
    session_local,
    user_onboarding_service,
    telegram_user: TelegramUser,
) -> HomeSnapshot:
    async with session_local.begin() as session:
        return await _ensure_home_snapshot(
            session,
            user_onboarding_service=user_onboarding_service,
            telegram_user=telegram_user,
        )


async def _resolve_friend_answer_context(
    *,
    result: AnswerSessionResult,
    snapshot: HomeSnapshot,
    resolve_opponent_label,
    friend_opponent_user_id,
) -> _FriendAnswerContext | None:
    if result.friend_challenge is None:
        return None

    challenge = result.friend_challenge
    opponent_label = await resolve_opponent_label(
        challenge=challenge,
        user_id=snapshot.user_id,
    )
    return _FriendAnswerContext(
        snapshot=snapshot,
        challenge=challenge,
        opponent_label=opponent_label,
        opponent_user_id=friend_opponent_user_id(
            challenge=challenge,
            user_id=snapshot.user_id,
        ),
    )


async def _send_invalid_friend_challenge_message(
    callback: CallbackQuery,
    *,
    message: Message,
) -> None:
    await message.answer(
        TEXTS_DE["msg.friend.challenge.invalid"],
        reply_markup=build_home_keyboard(),
    )
    await callback.answer()


def _build_friend_round_result_text(
    *,
    result: AnswerSessionResult,
    challenge: FriendChallengeSnapshot,
) -> str:
    return TEXTS_DE["msg.friend.challenge.round.result"].format(
        round_no=(result.friend_challenge_answered_round or challenge.current_round)
    )


async def _send_friend_progress_messages(
    message: Message,
    *,
    result: AnswerSessionResult,
    context: _FriendAnswerContext,
    now_utc: datetime,
    deps: _FriendAnswerDeps,
) -> None:
    await message.answer(
        deps.build_friend_score_text(
            challenge=context.challenge,
            user_id=context.snapshot.user_id,
            opponent_label=context.opponent_label,
        )
    )
    ttl_text = deps.build_friend_ttl_text(challenge=context.challenge, now_utc=now_utc)
    if ttl_text is not None:
        await message.answer(ttl_text)
    if result.friend_challenge_round_completed:
        await message.answer(
            _build_friend_round_result_text(
                result=result,
                challenge=context.challenge,
            )
        )


async def _maybe_notify_creator_turn(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    context: _FriendAnswerContext,
    now_utc: datetime,
    deps: _FriendAnswerDeps,
) -> None:
    if result.idempotent_replay or context.opponent_user_id is None:
        return
    if context.opponent_user_id != context.challenge.creator_user_id:
        return
    if not await _should_notify_creator_after_opponent_finished(
        session_local=deps.session_local,
        challenge_id=context.challenge.challenge_id,
        target_user_id=context.opponent_user_id,
    ):
        return

    push_reserved = await reserve_duel_push_slot(
        session_local=deps.session_local,
        challenge_id=context.challenge.challenge_id,
        target_user_id=context.opponent_user_id,
        now_utc=now_utc,
    )
    if not push_reserved:
        return

    await deps.notify_opponent(
        callback,
        opponent_user_id=context.opponent_user_id,
        text=TEXTS_DE["msg.friend.challenge.turn.reminder"],
        reply_markup=build_friend_challenge_start_keyboard(
            challenge_id=str(context.challenge.challenge_id)
        ),
    )


def _is_terminal_friend_challenge(challenge: FriendChallengeSnapshot) -> bool:
    return challenge.status in {"COMPLETED", "EXPIRED", "WALKOVER", "CANCELED"}


def _build_completion_callbacks(deps: _FriendAnswerDeps) -> FriendCompletionCallbacks:
    return FriendCompletionCallbacks(
        resolve_opponent_label=deps.resolve_opponent_label,
        notify_opponent=deps.notify_opponent,
        build_friend_score_text=deps.build_friend_score_text,
        build_friend_finish_text=deps.build_friend_finish_text,
        build_public_badge_label=deps.build_public_badge_label,
        build_friend_proof_card_text=deps.build_friend_proof_card_text,
        enqueue_friend_challenge_proof_cards=deps.enqueue_friend_challenge_proof_cards,
        build_series_progress_text=deps.build_series_progress_text,
    )


async def _handle_terminal_friend_challenge(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    context: _FriendAnswerContext,
    now_utc: datetime,
    deps: _FriendAnswerDeps,
) -> bool:
    if not _is_terminal_friend_challenge(context.challenge):
        return False

    await handle_completed_friend_challenge(
        callback,
        challenge=context.challenge,
        snapshot_user_id=context.snapshot.user_id,
        opponent_label=context.opponent_label,
        opponent_user_id=context.opponent_user_id,
        now_utc=now_utc,
        idempotent_replay=result.idempotent_replay,
        session_local=deps.session_local,
        game_session_service=deps.game_session_service,
        callbacks=_build_completion_callbacks(deps),
    )
    await callback.answer()
    return True


async def _handle_start_round_error(
    callback: CallbackQuery,
    *,
    message: Message,
    challenge: FriendChallengeSnapshot,
    error: Exception,
) -> None:
    if isinstance(error, FriendChallengeExpiredError):
        await message.answer(
            TEXTS_DE["msg.friend.challenge.expired"],
            reply_markup=build_friend_challenge_finished_keyboard(
                challenge_id=str(challenge.challenge_id)
            ),
        )
    else:
        await message.answer(
            TEXTS_DE["msg.friend.challenge.invalid"],
            reply_markup=build_home_keyboard(),
        )
    await callback.answer()


async def _start_followup_friend_round(
    callback: CallbackQuery,
    *,
    request: _FriendAnswerRequest,
    context: _FriendAnswerContext,
    now_utc: datetime,
    deps: _FriendAnswerDeps,
) -> _StartedFriendRoundPayload | None:
    async with deps.session_local.begin() as session:
        snapshot = await _ensure_home_snapshot(
            session,
            user_onboarding_service=deps.user_onboarding_service,
            telegram_user=request.telegram_user,
        )
        try:
            round_start = await deps.game_session_service.start_friend_challenge_round(
                session,
                user_id=snapshot.user_id,
                challenge_id=context.challenge.challenge_id,
                idempotency_key=f"start:friend:auto:{context.challenge.challenge_id}:{callback.id}",
                now_utc=now_utc,
            )
        except (
            FriendChallengeExpiredError,
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
            FriendChallengeCompletedError,
            FriendChallengeFullError,
        ) as error:
            await _handle_start_round_error(
                callback,
                message=request.message,
                challenge=context.challenge,
                error=error,
            )
            return None

    return _StartedFriendRoundPayload(
        snapshot=snapshot,
        round_start=round_start,
    )


async def _deliver_followup_friend_round(
    callback: CallbackQuery,
    *,
    message: Message,
    context: _FriendAnswerContext,
    started_round: _StartedFriendRoundPayload,
    deps: _FriendAnswerDeps,
) -> None:
    if started_round.round_start.start_result is not None:
        await deps.send_friend_round_question(
            callback,
            snapshot_free_energy=started_round.snapshot.free_energy,
            snapshot_paid_energy=started_round.snapshot.paid_energy,
            round_start=started_round.round_start,
        )
        return

    waiting_text = TEXTS_DE["msg.friend.challenge.all_answered.waiting"].format(
        total_rounds=context.challenge.total_rounds,
        opponent_label=context.opponent_label,
    )
    await message.answer(
        waiting_text,
        reply_markup=build_friend_challenge_back_keyboard(),
    )


async def _run_friend_answer_branch(
    callback: CallbackQuery,
    *,
    request: _FriendAnswerRequest,
    result: AnswerSessionResult,
    now_utc: datetime,
    deps: _FriendAnswerDeps,
) -> None:
    snapshot = await _load_home_snapshot(
        session_local=deps.session_local,
        user_onboarding_service=deps.user_onboarding_service,
        telegram_user=request.telegram_user,
    )
    context = await _resolve_friend_answer_context(
        result=result,
        snapshot=snapshot,
        resolve_opponent_label=deps.resolve_opponent_label,
        friend_opponent_user_id=deps.friend_opponent_user_id,
    )
    if context is None:
        await _send_invalid_friend_challenge_message(callback, message=request.message)
        return

    await _send_friend_progress_messages(
        request.message,
        result=result,
        context=context,
        now_utc=now_utc,
        deps=deps,
    )
    await _maybe_notify_creator_turn(
        callback,
        result=result,
        context=context,
        now_utc=now_utc,
        deps=deps,
    )
    if await _handle_terminal_friend_challenge(
        callback,
        result=result,
        context=context,
        now_utc=now_utc,
        deps=deps,
    ):
        return

    started_round = await _start_followup_friend_round(
        callback,
        request=request,
        context=context,
        now_utc=now_utc,
        deps=deps,
    )
    if started_round is None:
        return

    await _deliver_followup_friend_round(
        callback,
        message=request.message,
        context=context,
        started_round=started_round,
        deps=deps,
    )
    await callback.answer()


async def _should_notify_creator_after_opponent_finished(
    *,
    session_local,
    challenge_id,
    target_user_id: int,
) -> bool:
    async with session_local.begin() as session:
        challenge_row = await FriendChallengesRepo.get_by_id(session, challenge_id)
    return bool(
        challenge_row is not None
        and challenge_row.creator_user_id == target_user_id
        and challenge_row.opponent_answered_round == challenge_row.total_rounds
        and challenge_row.creator_answered_round == 0
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
