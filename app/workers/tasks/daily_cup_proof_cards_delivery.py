from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from aiogram.types import BufferedInputFile

from app.bot.keyboards.daily_cup import build_daily_cup_share_keyboard, build_daily_cup_share_url
from app.bot.texts.de import TEXTS_DE
from app.core.telegram_links import public_bot_link
from app.workers.tasks.daily_cup_proof_cards_text import build_caption
from app.workers.tasks.tournaments_proof_card_render import render_tournament_proof_card_png


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
        rounds_played=4,
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
