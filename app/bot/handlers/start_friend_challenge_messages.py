from __future__ import annotations

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_next_keyboard,
    build_friend_open_taken_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.core.config import get_settings

from .start_friend_challenge_models import (
    OutgoingStartMessage,
    StartFriendChallengeHandlingResult,
    StartFriendChallengePayloadContext,
    StartFriendChallengeRenderers,
)


def build_friend_challenge_error_result(
    error_key: str | None,
) -> StartFriendChallengeHandlingResult:
    normalized_key = error_key or "msg.friend.challenge.invalid"
    reply_markup = (
        build_friend_open_taken_keyboard()
        if normalized_key == "msg.friend.challenge.open.taken"
        else build_home_keyboard()
    )
    return StartFriendChallengeHandlingResult(
        handled=True,
        messages=[
            OutgoingStartMessage(
                text=TEXTS_DE[normalized_key],
                reply_markup=reply_markup,
            )
        ],
    )


async def build_started_friend_challenge_messages(
    context: StartFriendChallengePayloadContext,
    renderers: StartFriendChallengeRenderers,
    *,
    challenge_start,
) -> list[OutgoingStartMessage]:
    opponent_label = await renderers.resolve_opponent_label(
        challenge=challenge_start.snapshot,
        user_id=context.snapshot.user_id,
    )
    outgoing_messages = _build_welcome_messages(
        challenge_start=challenge_start,
        opponent_label=opponent_label,
    )
    outgoing_messages.append(
        _build_summary_message(
            context,
            renderers,
            challenge_start=challenge_start,
            opponent_label=opponent_label,
        )
    )
    question_message = _build_question_message(context, renderers, challenge_start=challenge_start)
    if question_message is not None:
        outgoing_messages.append(question_message)
    return outgoing_messages


def _build_welcome_messages(*, challenge_start, opponent_label: str) -> list[OutgoingStartMessage]:
    welcome_image_file_id = get_settings().resolved_welcome_image_file_id
    if not welcome_image_file_id:
        return []
    return [
        OutgoingStartMessage(
            text=(
                f"⚔️ {opponent_label} fordert dich heraus!\n"
                f"{challenge_start.snapshot.total_rounds} Fragen • Deutsch lernen"
            ),
            reply_markup=build_friend_challenge_next_keyboard(
                challenge_id=str(challenge_start.snapshot.challenge_id)
            ),
            photo=welcome_image_file_id,
        )
    ]


def _build_summary_message(
    context: StartFriendChallengePayloadContext,
    renderers: StartFriendChallengeRenderers,
    *,
    challenge_start,
    opponent_label: str,
) -> OutgoingStartMessage:
    summary_lines = _build_summary_lines(
        context,
        renderers,
        challenge_start=challenge_start,
        opponent_label=opponent_label,
    )
    return OutgoingStartMessage(
        text="\n".join(summary_lines),
        reply_markup=build_friend_challenge_back_keyboard(
            challenge=challenge_start.snapshot,
            user_id=context.snapshot.user_id,
        ),
    )


def _build_summary_lines(
    context: StartFriendChallengePayloadContext,
    renderers: StartFriendChallengeRenderers,
    *,
    challenge_start,
    opponent_label: str,
) -> list[str]:
    summary_lines = [
        TEXTS_DE["msg.friend.challenge.joined"],
        TEXTS_DE["msg.friend.challenge.with"].format(opponent_label=opponent_label),
        renderers.build_friend_plan_text(total_rounds=challenge_start.snapshot.total_rounds),
        TEXTS_DE["msg.friend.challenge.play.instant"].format(
            total_rounds=challenge_start.snapshot.total_rounds
        ),
        renderers.build_friend_score_text(
            challenge=challenge_start.snapshot,
            user_id=context.snapshot.user_id,
            opponent_label=opponent_label,
        ),
    ]
    ttl_text = renderers.build_friend_ttl_text(
        challenge=challenge_start.snapshot,
        now_utc=context.now_utc,
    )
    if ttl_text is not None:
        summary_lines.append(ttl_text)
    if challenge_start.waiting_for_opponent:
        summary_lines.append(TEXTS_DE["msg.friend.challenge.waiting"])
    if challenge_start.already_answered_current_round:
        summary_lines.append(TEXTS_DE["msg.friend.challenge.round.already.answered"])
    return summary_lines


def _build_question_message(
    context: StartFriendChallengePayloadContext,
    renderers: StartFriendChallengeRenderers,
    *,
    challenge_start,
) -> OutgoingStartMessage | None:
    if challenge_start.start_result is None:
        return None
    question_text = renderers.build_question_text(
        source="FRIEND_CHALLENGE",
        snapshot_free_energy=context.snapshot.free_energy,
        snapshot_paid_energy=context.snapshot.paid_energy,
        start_result=challenge_start.start_result,
    )
    return OutgoingStartMessage(
        text=question_text,
        reply_markup=build_quiz_keyboard(
            session_id=str(challenge_start.start_result.session.session_id),
            options=challenge_start.start_result.session.options,
        ),
        parse_mode="HTML",
    )
