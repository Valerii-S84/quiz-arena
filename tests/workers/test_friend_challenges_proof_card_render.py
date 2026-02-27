from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from PIL import Image

from app.workers.tasks.friend_challenges_proof_card_render import render_duel_proof_card_png


def test_render_duel_proof_card_png_has_expected_canvas_and_format() -> None:
    png_bytes = render_duel_proof_card_png(
        creator_name="Max",
        opponent_name="Anna",
        creator_score=10,
        opponent_score=8,
        total_rounds=12,
        completed_at=datetime(2026, 2, 27, 18, 0, tzinfo=timezone.utc),
    )

    image = Image.open(BytesIO(png_bytes))
    assert image.format == "PNG"
    assert image.size == (1080, 1080)
