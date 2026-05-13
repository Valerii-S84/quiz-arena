from __future__ import annotations

from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.duels import rollout as duel_rollout

from .start_friend_challenge_join import join_and_start_friend_challenge
from .start_friend_challenge_messages import (
    build_friend_challenge_error_result,
    build_started_friend_challenge_messages,
)
from .start_friend_challenge_models import (
    OutgoingStartMessage,
    StartFriendChallengeHandlingResult,
    StartFriendChallengePayloadContext,
    StartFriendChallengeRenderers,
)


async def handle_start_friend_challenge_payload(
    context: StartFriendChallengePayloadContext,
    renderers: StartFriendChallengeRenderers,
) -> StartFriendChallengeHandlingResult | None:
    if context.friend_invite_token is None and context.duel_challenge_id is None:
        return None
    if not duel_rollout.is_canonical_duels_enabled():
        return StartFriendChallengeHandlingResult(
            handled=True,
            messages=[
                OutgoingStartMessage(
                    text=TEXTS_DE["msg.duels.disabled"],
                    reply_markup=build_home_keyboard(),
                )
            ],
        )

    started_challenge, error_key = await join_and_start_friend_challenge(context)
    if started_challenge is None:
        return build_friend_challenge_error_result(error_key)

    outgoing_messages = await build_started_friend_challenge_messages(
        context,
        renderers,
        challenge_start=started_challenge.challenge_start,
    )
    return StartFriendChallengeHandlingResult(
        handled=True,
        messages=outgoing_messages,
        notify_creator=started_challenge.joined_now,
        notify_challenge=(
            started_challenge.challenge_start.snapshot if started_challenge.joined_now else None
        ),
        notify_joiner_user_id=context.snapshot.user_id if started_challenge.joined_now else None,
    )
