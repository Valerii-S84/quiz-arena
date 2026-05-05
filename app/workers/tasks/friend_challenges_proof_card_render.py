from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import ImageDraw

from app.workers.tasks.friend_challenges_proof_card_render_branding import (
    draw_brand_header,
    draw_meta,
    draw_title,
)
from app.workers.tasks.friend_challenges_proof_card_render_sections import (
    build_panel_theme,
    draw_name_panels,
    draw_scoreboard,
)
from app.workers.tasks.friend_challenges_proof_card_style import draw_radial_background, load_logo

_BERLIN_TZ = ZoneInfo("Europe/Berlin")


def _format_date(date_utc: datetime | None) -> str:
    resolved = date_utc or datetime.now(timezone.utc)
    return resolved.astimezone(_BERLIN_TZ).strftime("%d.%m.%Y")


def _winner_side(*, creator_score: int, opponent_score: int) -> str | None:
    if creator_score > opponent_score:
        return "creator"
    if opponent_score > creator_score:
        return "opponent"
    return None


def render_duel_proof_card_png(
    *,
    creator_name: str,
    opponent_name: str,
    creator_score: int,
    opponent_score: int,
    total_rounds: int,
    completed_at: datetime | None,
) -> bytes:
    image = draw_radial_background()
    draw = ImageDraw.Draw(image)
    winner = _winner_side(creator_score=creator_score, opponent_score=opponent_score)
    theme = build_panel_theme(winner=winner)
    draw_brand_header(image=image, draw=draw, logo=load_logo())
    draw_title(draw=draw)
    draw_name_panels(
        draw=draw,
        creator_name=creator_name,
        opponent_name=opponent_name,
        theme=theme,
    )
    draw_scoreboard(
        draw=draw,
        creator_score=creator_score,
        opponent_score=opponent_score,
        theme=theme,
    )
    draw_meta(
        draw=draw, total_rounds=max(1, int(total_rounds)), date_text=_format_date(completed_at)
    )

    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


if __name__ == "__main__":
    preview_png = render_duel_proof_card_png(
        creator_name="MaxMustermann",
        opponent_name="AnnaSchmidt",
        creator_score=10,
        opponent_score=8,
        total_rounds=7,
        completed_at=datetime.now(timezone.utc),
    )
    output = Path(__file__).resolve().parents[3] / "proof_card_preview.png"
    output.write_bytes(preview_png)
