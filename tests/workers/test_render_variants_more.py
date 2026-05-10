from __future__ import annotations

from datetime import datetime, timezone

from app.workers.tasks.tournaments_proof_card_render_variants import (
    render_arena_card,
    render_participant_card,
)


def test_render_participant_and_arena_variants_return_rgb_images() -> None:
    completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    participant = render_participant_card(
        player_label="Ada Lovelace",
        place=9,
        completed_at=completed_at,
        tournament_name=None,
        is_daily_arena=False,
    )
    arena = render_arena_card(
        player_label="Ada Lovelace",
        place=6,
        points="4.5",
        format_label="5 Fragen",
        completed_at=completed_at,
        tournament_name="Private Cup",
        rounds_played=0,
        is_daily_arena=False,
    )

    assert participant.mode == "RGB"
    assert arena.mode == "RGB"
    assert participant.size == arena.size
