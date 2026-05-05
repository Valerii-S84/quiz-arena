from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.arena_revanche_delivery import (
    create_and_send_revanche,
    resolve_user_label,
)
from app.bot.keyboards.duels import (
    build_arena_guard_back_keyboard,
    build_arena_revanche_confirm_keyboard,
    build_duel_paywall_keyboard,
)
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.analytics import (
    ARENA_EVENT_ARENA_REVANCHE_CLICKED,
    build_arena_event_payload,
    emit_arena_analytics_event,
)
from app.game.arena_duels.errors import (
    ArenaDuelAccessError,
    ArenaDuelNotFoundError,
    ArenaDuelPaymentRequiredError,
)


async def handle_arena_revanche_confirm(
    callback: CallbackQuery,
    *,
    arena_revanche_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    load_arena_revanche_context,
) -> None:
    source_attempt_id = _parse_source_attempt_id(
        callback,
        pattern=arena_revanche_re,
        parse_uuid_callback=parse_uuid_callback,
    )
    if source_attempt_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            context = await load_arena_revanche_context(
                session,
                sender_user_id=snapshot.user_id,
                source_attempt_id=source_attempt_id,
            )
        except (ArenaDuelAccessError, ArenaDuelNotFoundError):
            await _send_revanche_blocked(callback)
            return
        opponent_label = await resolve_user_label(
            session=session,
            user_onboarding_service=user_onboarding_service,
            user_id=context.receiver_user_id,
        )
        await emit_arena_analytics_event(
            session,
            event_type=ARENA_EVENT_ARENA_REVANCHE_CLICKED,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload=build_arena_event_payload(
                user_id=snapshot.user_id,
                arena_duel_id=getattr(context, "arena_duel_id", None),
                attempt_id=source_attempt_id,
            ),
        )

    await callback.message.answer(
        TEXTS_DE["msg.duels.revanche.confirm"].format(opponent_label=opponent_label),
        reply_markup=build_arena_revanche_confirm_keyboard(
            source_attempt_id=str(source_attempt_id),
        ),
    )
    await callback.answer()


async def handle_arena_revanche_send(
    callback: CallbackQuery,
    *,
    arena_revanche_send_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    prepare_arena_revanche_request,
    record_arena_revanche_sent,
    cleanup_arena_revanche_request,
) -> None:
    source_attempt_id = _parse_source_attempt_id(
        callback,
        pattern=arena_revanche_send_re,
        parse_uuid_callback=parse_uuid_callback,
    )
    if source_attempt_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    try:
        opponent_label = await create_and_send_revanche(
            callback,
            session_local=session_local,
            user_onboarding_service=user_onboarding_service,
            prepare_arena_revanche_request=prepare_arena_revanche_request,
            record_arena_revanche_sent=record_arena_revanche_sent,
            cleanup_arena_revanche_request=cleanup_arena_revanche_request,
            source_attempt_id=source_attempt_id,
            now_utc=datetime.now(timezone.utc),
        )
    except ArenaDuelPaymentRequiredError:
        await _send_duel_paywall(callback)
        return
    except (ArenaDuelAccessError, ArenaDuelNotFoundError):
        await _send_revanche_blocked(callback)
        return
    except Exception:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    await callback.message.answer(
        TEXTS_DE["msg.duels.revanche.sent"].format(opponent_label=opponent_label),
        reply_markup=build_arena_guard_back_keyboard(),
    )
    await callback.answer()


async def _send_duel_paywall(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(
            TEXTS_DE["msg.duels.limit.reached"],
            reply_markup=build_duel_paywall_keyboard(),
        )
    await callback.answer()


async def _send_revanche_blocked(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(
            TEXTS_DE["msg.duels.revanche.blocked"],
            reply_markup=build_arena_guard_back_keyboard(),
        )
    await callback.answer()


def _parse_source_attempt_id(callback: CallbackQuery, *, pattern, parse_uuid_callback):
    if callback.data is None:
        return None
    return parse_uuid_callback(pattern=pattern, callback_data=callback.data)
