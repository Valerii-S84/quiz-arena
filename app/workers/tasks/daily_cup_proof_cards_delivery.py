from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiogram.types import BufferedInputFile

from app.bot.keyboards.daily_cup import build_daily_cup_share_keyboard, build_daily_cup_share_url
from app.bot.texts.de import TEXTS_DE
from app.core.telegram_links import public_bot_link
from app.workers.tasks.daily_cup_proof_cards_text import build_caption
from app.workers.tasks.tournaments_proof_card_render import render_tournament_proof_card_png


@dataclass(frozen=True, slots=True)
class DailyCupProofCardDeliveryResult:
    sent: int
    cached_reused: int
    failed: int
    sent_user_ids: set[int]
    new_file_ids: dict[int, str]


async def send_daily_cup_proof_card(
    *,
    bot,
    tournament_id: str,
    user_id: int,
    chat_id: int,
    place: int,
    points: str,
    participants_total: int,
    cached_file_id: str | None,
    player_label: str,
    now_utc: datetime,
    rounds_played: int,
    render_card_png: Callable[..., bytes] = render_tournament_proof_card_png,
) -> tuple[bool, bool, str | None]:
    caption = build_caption(place=place, points=points)
    share_url = build_daily_cup_share_url(
        base_link=public_bot_link(),
        share_text=TEXTS_DE["msg.daily_cup.share_template"].format(
            place=place,
            total=participants_total,
            points=points,
        ),
    )
    keyboard = build_daily_cup_share_keyboard(tournament_id=tournament_id, share_url=share_url)
    if cached_file_id:
        await bot.send_photo(
            chat_id=chat_id,
            photo=cached_file_id,
            caption=caption,
            reply_markup=keyboard,
        )
        return True, True, None

    card_png = render_card_png(
        player_label=player_label,
        place=place,
        points=points,
        format_label="7 Fragen",
        completed_at=now_utc,
        tournament_name="Daily Arena Cup",
        rounds_played=rounds_played,
        is_daily_arena=True,
    )
    message = await bot.send_photo(
        chat_id=chat_id,
        photo=BufferedInputFile(card_png, filename=f"daily_cup_{tournament_id}_{user_id}.png"),
        caption=caption,
        reply_markup=keyboard,
    )
    file_id = message.photo[-1].file_id if message.photo else None
    return True, False, file_id


async def deliver_daily_cup_proof_cards(
    *,
    context: Any,
    bot: Any,
    tournament_id: str,
    now_utc: datetime,
    send_proof_card_fn: Callable[..., Any],
    render_card_png: Callable[..., bytes] = render_tournament_proof_card_png,
    logger: Any,
) -> DailyCupProofCardDeliveryResult:
    sent = 0
    cached_reused = 0
    failed = 0
    new_file_ids: dict[int, str] = {}
    sent_user_ids: set[int] = set()

    for row in context.participants:
        current_user_id = int(row.user_id)
        chat_id = context.telegram_targets.get(current_user_id)
        if chat_id is None:
            failed += 1
            continue
        participant_row = context.participant_rows[current_user_id]
        if participant_row.proof_card_sent:
            continue
        place = context.standings_user_ids.index(current_user_id) + 1
        points = context.points_by_user.get(current_user_id, "0")
        try:
            delivered, reused_cached, file_id = await send_proof_card_fn(
                bot=bot,
                tournament_id=tournament_id,
                user_id=current_user_id,
                chat_id=chat_id,
                place=place,
                points=points,
                participants_total=context.participants_total,
                cached_file_id=participant_row.proof_card_file_id,
                player_label=context.user_labels.get(current_user_id, "Spieler"),
                now_utc=now_utc,
                rounds_played=context.rounds_played,
                render_card_png=render_card_png,
            )
            if not delivered:
                continue
            sent += 1
            cached_reused += int(reused_cached)
            sent_user_ids.add(current_user_id)
            if file_id is not None:
                new_file_ids[current_user_id] = file_id
        except Exception as exc:
            logger.warning(
                "daily_cup_proof_card_send_failed",
                tournament_id=tournament_id,
                user_id=current_user_id,
                error_type=type(exc).__name__,
            )
            failed += 1

    return DailyCupProofCardDeliveryResult(
        sent=sent,
        cached_reused=cached_reused,
        failed=failed,
        sent_user_ids=sent_user_ids,
        new_file_ids=new_file_ids,
    )


__all__ = [
    "DailyCupProofCardDeliveryResult",
    "deliver_daily_cup_proof_cards",
    "send_daily_cup_proof_card",
]
