from __future__ import annotations

from io import BytesIO

from PIL import Image

from app.workers.tasks.tournaments_proof_card_render import render_tournament_proof_card_png


def test_render_tournament_proof_card_top3_variant_differs_from_regular() -> None:
    top1_png = render_tournament_proof_card_png(
        player_label="Spieler Eins",
        place=1,
        points="3",
        format_label="12 Fragen",
        completed_at=None,
    )
    regular_png = render_tournament_proof_card_png(
        player_label="Spieler Vier",
        place=4,
        points="1",
        format_label="12 Fragen",
        completed_at=None,
    )

    assert top1_png != regular_png
    image = Image.open(BytesIO(top1_png))
    assert image.size == (1080, 1080)
