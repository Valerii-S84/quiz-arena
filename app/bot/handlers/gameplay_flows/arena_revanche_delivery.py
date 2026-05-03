from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_views import _format_user_label
from app.bot.keyboards.friend_challenge import build_friend_challenge_next_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.errors import ArenaDuelAccessError
from app.game.arena_duels.revanche_types import ArenaRevancheRequest


@dataclass(frozen=True, slots=True)
class RevancheDelivery:
    opponent_label: str
    already_sent: bool
    sender_label: str | None = None
    opponent_chat_id: int | None = None
    challenge_id: UUID | None = None
    request: ArenaRevancheRequest | None = None


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
    delivery = await persist_revanche_delivery(
        callback,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        prepare_arena_revanche_request=prepare_arena_revanche_request,
        record_arena_revanche_sent=record_arena_revanche_sent,
        source_attempt_id=source_attempt_id,
        now_utc=now_utc,
    )
    if delivery.already_sent:
        return delivery.opponent_label
    if (
        delivery.sender_label is None
        or delivery.opponent_chat_id is None
        or delivery.challenge_id is None
    ):
        raise ArenaDuelAccessError

    await bot.send_message(
        chat_id=delivery.opponent_chat_id,
        text=TEXTS_DE["msg.duels.revanche.incoming"].format(
            opponent_label=delivery.sender_label,
        ),
        reply_markup=build_friend_challenge_next_keyboard(
            challenge_id=str(delivery.challenge_id),
        ),
    )
    if delivery.request is None:
        raise ArenaDuelAccessError
    async with session_local.begin() as session:
        await record_arena_revanche_sent(
            session,
            request=delivery.request,
            happened_at=now_utc,
        )
    return delivery.opponent_label


async def persist_revanche_delivery(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    prepare_arena_revanche_request,
    record_arena_revanche_sent,
    source_attempt_id: UUID,
    now_utc: datetime,
) -> RevancheDelivery:
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
            return RevancheDelivery(opponent_label=opponent_label, already_sent=True)
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
        return RevancheDelivery(
            opponent_label=opponent_label,
            already_sent=False,
            sender_label=sender_label,
            opponent_chat_id=opponent.telegram_user_id,
            challenge_id=request.challenge.challenge_id,
            request=request,
        )


async def resolve_user_label(*, session, user_onboarding_service, user_id: int) -> str:
    user = await user_onboarding_service.get_by_id(session, user_id)
    if user is None:
        return f"Spieler #{user_id}"
    return _format_user_label(
        username=user.username,
        first_name=user.first_name,
        fallback=f"Spieler #{user_id}",
    )
