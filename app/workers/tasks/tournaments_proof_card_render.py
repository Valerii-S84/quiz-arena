from __future__ import annotations

from datetime import datetime
from io import BytesIO

from app.workers.tasks.tournaments_proof_card_render_variants import (
    render_arena_card,
    render_champion_card,
    render_participant_card,
)


def render_tournament_proof_card_png(
    *,
    player_label: str,
    place: int,
    points: str,
    format_label: str,
    completed_at: datetime | None,
    tournament_name: str | None = None,
    rounds_played: int | None = None,
    is_daily_arena: bool = False,
) -> bytes:
    if place <= 3:
        image = render_champion_card(
            player_label=player_label,
            place=place,
            points=points,
            format_label=format_label,
            completed_at=completed_at,
            tournament_name=tournament_name,
            rounds_played=rounds_played,
            is_daily_arena=is_daily_arena,
        )
    elif place <= 10:
        image = render_arena_card(
            player_label=player_label,
            place=place,
            points=points,
            format_label=format_label,
            completed_at=completed_at,
            tournament_name=tournament_name,
            rounds_played=rounds_played,
            is_daily_arena=is_daily_arena,
        )
    else:
        image = render_participant_card(
            player_label=player_label,
            place=place,
            completed_at=completed_at,
            tournament_name=tournament_name,
            is_daily_arena=is_daily_arena,
        )

    buffer = BytesIO()
    image.save(buffer, format="PNG", compress_level=1)
    return buffer.getvalue()
