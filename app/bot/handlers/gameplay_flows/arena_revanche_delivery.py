from __future__ import annotations

from datetime import datetime
from uuid import UUID

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_views import _format_user_label
from app.bot.keyboards.friend_challenge import build_friend_challenge_next_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.errors import ArenaDuelAccessError


async def create_and_send_revanche(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    prepare_arena_revanche_request,
    record_arena_revanche_sent,
    source_attempt_id: UUID,
    now_utc: datetime,
) -> str:
    bot = callback.bot
    assert bot is not None
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        request = await prepare_arena_revanche_request(
            session,
            sender_user_id=snapshot.user_id,
            source_attempt_id=source_attempt_id,
            now_utc=now_utc,
        )
        opponent_label = await resolve_user_label(
            session=session,
            user_onboarding_service=user_onboarding_service,
            user_id=request.context.receiver_user_id,
        )
        if request.already_sent:
            return opponent_label
        if request.challenge is None:
            raise ArenaDuelAccessError
        sender_label = await resolve_user_label(
            session=session,
            user_onboarding_service=user_onboarding_service,
            user_id=snapshot.user_id,
        )
        opponent = await user_onboarding_service.get_by_id(
            session,
            request.context.receiver_user_id,
        )
        if opponent is None:
            raise ArenaDuelAccessError
        await bot.send_message(
            chat_id=opponent.telegram_user_id,
            text=TEXTS_DE["msg.duels.revanche.incoming"].format(opponent_label=sender_label),
            reply_markup=build_friend_challenge_next_keyboard(
                challenge_id=str(request.challenge.challenge_id),
            ),
        )
        await record_arena_revanche_sent(session, request=request, happened_at=now_utc)
        return opponent_label


async def resolve_user_label(*, session, user_onboarding_service, user_id: int) -> str:
    user = await user_onboarding_service.get_by_id(session, user_id)
    if user is None:
        return f"Spieler #{user_id}"
    return _format_user_label(
        username=user.username,
        first_name=user.first_name,
        fallback=f"Spieler #{user_id}",
    )
