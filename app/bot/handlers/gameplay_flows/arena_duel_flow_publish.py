from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.duels import build_arena_back_keyboard, build_arena_published_keyboard
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.errors import ArenaDuelAccessError, ArenaDuelIncompleteError
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeArenaPublishBaselineRequiredError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)

from .arena_duel_flow_publish_support import (
    emit_friend_publish_events,
    format_published_duel_score_line,
)
from .arena_duel_flow_support import extract_start_result


async def handle_arena_publish_friend(
    callback: CallbackQuery,
    *,
    friend_challenge_id,
    session_local,
    user_onboarding_service,
    publish_friend_challenge_to_arena,
    emit_arena_analytics_event,
    start_friend_challenge_round=None,
    build_question_text=None,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    invalid_state = False
    published_duel = None
    baseline_round_start = None
    snapshot = None
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            published_duel = await publish_friend_challenge_to_arena(
                session,
                user_id=snapshot.user_id,
                friend_challenge_id=friend_challenge_id,
                now_utc=now_utc,
            )
            await emit_friend_publish_events(
                session=session,
                emit_arena_analytics_event=emit_arena_analytics_event,
                user_id=snapshot.user_id,
                friend_challenge_id=friend_challenge_id,
                published_duel=published_duel,
                now_utc=now_utc,
            )
        except FriendChallengeArenaPublishBaselineRequiredError:
            if start_friend_challenge_round is None:
                invalid_state = True
            else:
                baseline_round_start = await _start_missing_baseline(
                    session=session,
                    start_friend_challenge_round=start_friend_challenge_round,
                    user_id=snapshot.user_id,
                    friend_challenge_id=friend_challenge_id,
                    callback_id=callback.id,
                    now_utc=now_utc,
                )
                invalid_state = baseline_round_start is None
        except (
            ArenaDuelAccessError,
            ArenaDuelIncompleteError,
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
        ):
            invalid_state = True

    if invalid_state:
        await callback.message.answer(
            TEXTS_DE["msg.duels.arena.friend_publish.invalid"],
            reply_markup=build_arena_back_keyboard(),
        )
        await callback.answer()
        return
    if baseline_round_start is not None:
        if build_question_text is None or snapshot is None:
            await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
            return
        start_result = extract_start_result(baseline_round_start)
        if start_result is None:
            await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
            return
        await callback.message.answer(
            build_question_text(
                source="FRIEND_CHALLENGE",
                snapshot_free_energy=snapshot.free_energy,
                snapshot_paid_energy=snapshot.paid_energy,
                start_result=start_result,
            ),
            reply_markup=build_quiz_keyboard(
                session_id=str(start_result.session.session_id),
                options=start_result.session.options,
            ),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    score_line = format_published_duel_score_line(published_duel)
    if score_line is None or published_duel is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.arena.friend_published"].format(score_line=score_line),
        reply_markup=build_arena_published_keyboard(duel_id=str(published_duel.duel_id)),
    )
    await callback.answer()


async def _start_missing_baseline(
    *,
    session,
    start_friend_challenge_round,
    user_id: int,
    friend_challenge_id,
    callback_id: str,
    now_utc: datetime,
):
    try:
        return await start_friend_challenge_round(
            session,
            user_id=user_id,
            challenge_id=friend_challenge_id,
            idempotency_key=f"start:friend:arena_publish:{friend_challenge_id}:{callback_id}",
            now_utc=now_utc,
        )
    except (
        FriendChallengeNotFoundError,
        FriendChallengeAccessError,
        FriendChallengeCompletedError,
        FriendChallengeExpiredError,
        FriendChallengeFullError,
    ):
        return None
