from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.duels import (
    ArenaDuelButton,
    build_arena_empty_keyboard,
    build_arena_list_keyboard,
)
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.analytics import (
    ARENA_EVENT_ARENA_OPENED,
    build_arena_event_payload,
    emit_arena_analytics_event,
)
from app.game.arena_duels.types import ArenaActiveDuelSnapshot

from .arena_duel_flow_support import format_score_line, resolve_arena_user_label

ARENA_MARKERS = ("🔥", "👑", "⚡")


async def handle_arena_open(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    list_active_arena_duels,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        active_duels = await list_active_arena_duels(session, now_utc=now_utc)
        items = await _build_arena_list_items(
            session=session,
            user_onboarding_service=user_onboarding_service,
            active_duels=active_duels,
        )
        await emit_arena_analytics_event(
            session,
            event_type=ARENA_EVENT_ARENA_OPENED,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload=build_arena_event_payload(user_id=snapshot.user_id, action="open"),
        )

    if not items:
        await callback.message.answer(
            TEXTS_DE["msg.duels.arena.empty"],
            reply_markup=build_arena_empty_keyboard(),
        )
        await callback.answer()
        return

    await callback.message.answer(
        TEXTS_DE["msg.duels.arena.list"].format(duels=_format_arena_list(active_duels, items)),
        reply_markup=build_arena_list_keyboard(duels=items),
    )
    await callback.answer()


async def _build_arena_list_items(
    *,
    session,
    user_onboarding_service,
    active_duels: Sequence[ArenaActiveDuelSnapshot],
) -> tuple[ArenaDuelButton, ...]:
    items: list[ArenaDuelButton] = []
    for index, duel in enumerate(active_duels):
        label = await resolve_arena_user_label(
            session=session,
            user_onboarding_service=user_onboarding_service,
            user_id=duel.creator_user_id,
        )
        items.append(
            ArenaDuelButton(
                duel_id=str(duel.duel_id),
                label=label,
                marker=ARENA_MARKERS[index % len(ARENA_MARKERS)],
            )
        )
    return tuple(items)


def _format_arena_list(
    active_duels: Sequence[ArenaActiveDuelSnapshot],
    items: Sequence[ArenaDuelButton],
) -> str:
    lines: list[str] = []
    for duel, item in zip(active_duels, items, strict=True):
        lines.extend(
            (
                item.marker + " " + item.label,
                format_score_line(score=duel.score, time_ms=duel.time_ms),
                "",
            )
        )
    return "\n".join(lines).strip()
