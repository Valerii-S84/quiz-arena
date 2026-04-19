from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.handlers.gameplay_flows import friend_answer_flow_followup
from app.bot.handlers.gameplay_flows.friend_answer_completion_flow import FriendCompletionCallbacks
from app.bot.keyboards.friend_challenge import build_friend_challenge_start_keyboard
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import AnswerSessionResult, FriendChallengeSnapshot
from app.services.user_onboarding import HomeSnapshot


@dataclass(slots=True)
class FriendAnswerContext:
    snapshot: HomeSnapshot
    challenge: FriendChallengeSnapshot
    opponent_label: str
    opponent_user_id: int | None


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
) -> FriendAnswerContext | None:
    if result.friend_challenge is None:
        return None

    challenge = result.friend_challenge
    opponent_label = await resolve_opponent_label(
        challenge=challenge,
        user_id=snapshot.user_id,
    )
    return FriendAnswerContext(
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
    context: FriendAnswerContext,
    now_utc: datetime,
    deps,
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


async def _should_notify_creator_after_opponent_finished(
    *,
    session_local,
    challenge_id,
    target_user_id: int,
    friend_challenges_repo,
) -> bool:
    async with session_local.begin() as session:
        challenge_row = await friend_challenges_repo.get_by_id(session, challenge_id)
    return bool(
        challenge_row is not None
        and challenge_row.creator_user_id == target_user_id
        and challenge_row.opponent_answered_round == challenge_row.total_rounds
        and challenge_row.creator_answered_round == 0
    )


async def _maybe_notify_creator_turn(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    context: FriendAnswerContext,
    now_utc: datetime,
    deps,
    friend_challenges_repo,
    reserve_duel_push_slot,
) -> None:
    if result.idempotent_replay or context.opponent_user_id is None:
        return
    if context.opponent_user_id != context.challenge.creator_user_id:
        return
    if not await _should_notify_creator_after_opponent_finished(
        session_local=deps.session_local,
        challenge_id=context.challenge.challenge_id,
        target_user_id=context.opponent_user_id,
        friend_challenges_repo=friend_challenges_repo,
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


def _build_completion_callbacks(deps) -> FriendCompletionCallbacks:
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
    context: FriendAnswerContext,
    now_utc: datetime,
    deps,
    handle_completed_friend_challenge,
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


async def run_friend_answer_branch(
    callback: CallbackQuery,
    *,
    message: Message,
    telegram_user: TelegramUser,
    result: AnswerSessionResult,
    now_utc: datetime,
    deps,
    friend_challenges_repo,
    reserve_duel_push_slot,
    handle_completed_friend_challenge,
) -> None:
    snapshot = await _load_home_snapshot(
        session_local=deps.session_local,
        user_onboarding_service=deps.user_onboarding_service,
        telegram_user=telegram_user,
    )
    context = await _resolve_friend_answer_context(
        result=result,
        snapshot=snapshot,
        resolve_opponent_label=deps.resolve_opponent_label,
        friend_opponent_user_id=deps.friend_opponent_user_id,
    )
    if context is None:
        await _send_invalid_friend_challenge_message(callback, message=message)
        return

    await _send_friend_progress_messages(
        message,
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
        friend_challenges_repo=friend_challenges_repo,
        reserve_duel_push_slot=reserve_duel_push_slot,
    )
    if await _handle_terminal_friend_challenge(
        callback,
        result=result,
        context=context,
        now_utc=now_utc,
        deps=deps,
        handle_completed_friend_challenge=handle_completed_friend_challenge,
    ):
        return

    started_round = await friend_answer_flow_followup.start_followup_friend_round(
        callback,
        message=message,
        telegram_user=telegram_user,
        context=context,
        now_utc=now_utc,
        deps=deps,
    )
    if started_round is None:
        return

    await friend_answer_flow_followup.deliver_followup_friend_round(
        callback,
        message=message,
        context=context,
        started_round=started_round,
        deps=deps,
    )
    await callback.answer()
