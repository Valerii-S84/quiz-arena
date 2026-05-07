from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from aiogram.types import CallbackQuery

from app.bot.keyboards.duels import build_arena_accept_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.errors import (
    ArenaDuelAccessError,
    ArenaDuelAlreadyAttemptedError,
    ArenaDuelExpiredError,
    ArenaDuelNotFoundError,
    ArenaDuelOwnAttemptError,
)
from app.game.arena_duels.types import ArenaActiveDuelSnapshot

from .arena_duel_flow_support import (
    build_arena_guard_keyboard,
    format_score_line,
    parse_arena_duel_id,
    resolve_arena_user_label,
    send_arena_guard,
)


@dataclass(frozen=True, slots=True)
class ArenaAcceptScreen:
    duel: ArenaActiveDuelSnapshot | None
    opponent_label: str = ""
    guard_text_key: str | None = None


async def handle_arena_accept_preview(
    callback: CallbackQuery,
    *,
    arena_accept_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    get_arena_duel_accept_preview,
) -> None:
    duel_id = parse_arena_duel_id(
        callback,
        pattern=arena_accept_re,
        parse_uuid_callback=parse_uuid_callback,
    )
    if duel_id is None or callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        screen = await _load_arena_accept_screen(
            session=session,
            telegram_user=callback.from_user,
            user_onboarding_service=user_onboarding_service,
            get_arena_duel_accept_preview=get_arena_duel_accept_preview,
            duel_id=duel_id,
            now_utc=now_utc,
        )

    if screen.guard_text_key is not None:
        await send_arena_guard(
            callback,
            text_key=screen.guard_text_key,
            reply_markup=build_arena_guard_keyboard(screen.guard_text_key),
        )
        return
    if screen.duel is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    await callback.message.answer(
        TEXTS_DE["msg.duels.arena.accept"].format(
            opponent_label=screen.opponent_label,
            score_line=format_score_line(
                score=screen.duel.score,
                time_ms=screen.duel.time_ms,
            ),
        ),
        reply_markup=build_arena_accept_keyboard(duel_id=str(screen.duel.duel_id)),
    )
    await callback.answer()


async def _load_arena_accept_screen(
    *,
    session,
    telegram_user,
    user_onboarding_service,
    get_arena_duel_accept_preview,
    duel_id: UUID,
    now_utc: datetime,
) -> ArenaAcceptScreen:
    snapshot = await user_onboarding_service.ensure_home_snapshot(
        session,
        telegram_user=telegram_user,
    )
    try:
        duel = await get_arena_duel_accept_preview(
            session,
            duel_id=duel_id,
            user_id=snapshot.user_id,
            now_utc=now_utc,
        )
    except ArenaDuelOwnAttemptError:
        return ArenaAcceptScreen(duel=None, guard_text_key="msg.duels.arena.own")
    except ArenaDuelAlreadyAttemptedError:
        return ArenaAcceptScreen(duel=None, guard_text_key="msg.duels.arena.already_played")
    except (ArenaDuelExpiredError, ArenaDuelNotFoundError, ArenaDuelAccessError):
        return ArenaAcceptScreen(duel=None, guard_text_key="msg.duels.arena.expired")

    opponent_label = await resolve_arena_user_label(
        session=session,
        user_onboarding_service=user_onboarding_service,
        user_id=duel.creator_user_id,
    )
    return ArenaAcceptScreen(duel=duel, opponent_label=opponent_label)
