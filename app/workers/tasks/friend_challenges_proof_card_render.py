from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from app.workers.tasks.friend_challenges_proof_card_style import (
    BRAND,
    CARD_SIZE,
    GOLD,
    LOSER_GRAY,
    PANEL_DARK,
    PANEL_GOLD,
    PANEL_SILVER,
    SILVER,
    TEXT_MAIN,
    TEXT_MUTED,
    TITLE,
    center_x,
    center_x_in_box,
    draw_fade_line,
    draw_radial_background,
    draw_spaced_text,
    fit_name_font,
    font,
    load_logo,
    text_width,
)

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

    logo = load_logo()
    alpha_extrema: object | None = None
    if logo is not None and "A" in logo.getbands():
        alpha_extrema = logo.getchannel("A").getextrema()
    alpha_min = 255
    if isinstance(alpha_extrema, tuple) and alpha_extrema:
        first_item = alpha_extrema[0]
        if isinstance(first_item, tuple):
            alpha_min = int(first_item[0])
        else:
            alpha_min = int(first_item)
    elif isinstance(alpha_extrema, (int, float)):
        alpha_min = int(alpha_extrema)

    if logo is not None and "A" in logo.getbands() and alpha_min < 250:
        logo_height = 120
        logo_width = max(1, int((logo.width / max(1, logo.height)) * logo_height))
        if logo_width > 760:
            logo_width = 760
            logo_height = max(1, int((logo.height / max(1, logo.width)) * logo_width))
        logo_resized = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
        image.alpha_composite(logo_resized, ((int((CARD_SIZE - logo_width) / 2)), 54))
    else:
        brand_font = font(size=76, bold=True)
        brand_x = center_x(draw=draw, text=BRAND, font_obj=brand_font, tracking=6)
        draw_spaced_text(
            draw,
            text=BRAND,
            x=brand_x + 2,
            y=76,
            font_obj=brand_font,
            fill=(0, 0, 0, 160),
            tracking=6,
        )
        draw_spaced_text(
            draw,
            text=BRAND,
            x=brand_x,
            y=74,
            font_obj=brand_font,
            fill=(224, 229, 238, 255),
            tracking=6,
        )

    title_font = font(size=84, bold=True)
    title_x = center_x(draw=draw, text=TITLE, font_obj=title_font, tracking=5)
    draw_spaced_text(
        draw,
        text=TITLE,
        x=title_x + 2,
        y=228,
        font_obj=title_font,
        fill=(0, 0, 0, 153),
        tracking=5,
    )
    draw_spaced_text(
        draw,
        text=TITLE,
        x=title_x,
        y=226,
        font_obj=title_font,
        fill=TEXT_MAIN,
        tracking=5,
    )

    panel_top = 362
    panel_height = 226
    left_panel = (64, panel_top, 508, panel_top + panel_height)
    right_panel = (572, panel_top, 1016, panel_top + panel_height)

    winner = _winner_side(creator_score=creator_score, opponent_score=opponent_score)
    if winner == "creator":
        left_border, right_border = GOLD, (102, 102, 102, 255)
        left_fill, right_fill = PANEL_GOLD, PANEL_DARK
        left_name_color, right_name_color = GOLD, LOSER_GRAY
        left_label = creator_name
        right_label = opponent_name
        left_score_color, right_score_color = GOLD, LOSER_GRAY
    elif winner == "opponent":
        left_border, right_border = (102, 102, 102, 255), GOLD
        left_fill, right_fill = PANEL_DARK, PANEL_GOLD
        left_name_color, right_name_color = LOSER_GRAY, GOLD
        left_label = creator_name
        right_label = opponent_name
        left_score_color, right_score_color = LOSER_GRAY, GOLD
    else:
        left_border = right_border = SILVER
        left_fill = right_fill = PANEL_SILVER
        left_name_color = right_name_color = SILVER
        left_label = creator_name
        right_label = opponent_name
        left_score_color = right_score_color = SILVER

    draw.rounded_rectangle(left_panel, radius=34, fill=left_fill, outline=left_border, width=8)
    draw.rounded_rectangle(right_panel, radius=34, fill=right_fill, outline=right_border, width=8)

    left_name, left_font = fit_name_font(name=left_label, draw=draw, bold=True, max_width=390)
    right_name, right_font = fit_name_font(name=right_label, draw=draw, bold=True, max_width=390)
    draw.text(
        (
            center_x_in_box(
                draw=draw,
                text=left_name,
                font_obj=left_font,
                left=left_panel[0],
                right=left_panel[2],
            ),
            446,
        ),
        left_name,
        font=left_font,
        fill=left_name_color,
    )
    draw.text(
        (
            center_x_in_box(
                draw=draw,
                text=right_name,
                font_obj=right_font,
                left=right_panel[0],
                right=right_panel[2],
            ),
            446,
        ),
        right_name,
        font=right_font,
        fill=right_name_color,
    )

    draw_fade_line(draw, y=618, width=600, color=(255, 215, 0), alpha=200)

    score_font = font(size=210, bold=True)
    left_score = str(creator_score)
    right_score = str(opponent_score)
    colon = " : "
    left_width = text_width(draw=draw, text=left_score, font_obj=score_font)
    colon_width = text_width(draw=draw, text=colon, font_obj=score_font)
    right_width = text_width(draw=draw, text=right_score, font_obj=score_font)
    score_x = int((CARD_SIZE - (left_width + colon_width + right_width)) / 2)
    score_y = 652
    draw.text((score_x, score_y), left_score, font=score_font, fill=left_score_color)
    draw.text((score_x + left_width, score_y), colon, font=score_font, fill=(255, 255, 255, 255))
    draw.text(
        (score_x + left_width + colon_width, score_y),
        right_score,
        font=score_font,
        fill=right_score_color,
    )

    meta_font = font(size=44, bold=False)
    format_text = f"FORMAT: {max(1, int(total_rounds))} FRAGEN"
    date_text = f"DATUM: {_format_date(completed_at)}"
    draw.text(
        (center_x(draw=draw, text=format_text, font_obj=meta_font), 906),
        format_text,
        font=meta_font,
        fill=TEXT_MUTED,
    )
    draw.text(
        (center_x(draw=draw, text=date_text, font_obj=meta_font), 958),
        date_text,
        font=meta_font,
        fill=TEXT_MUTED,
    )
    draw_fade_line(draw, y=1016, width=680, color=(255, 215, 0), alpha=180)

    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


if __name__ == "__main__":
    preview_png = render_duel_proof_card_png(
        creator_name="MaxMustermann",
        opponent_name="AnnaSchmidt",
        creator_score=10,
        opponent_score=8,
        total_rounds=12,
        completed_at=datetime.now(timezone.utc),
    )
    output = Path(__file__).resolve().parents[3] / "proof_card_preview.png"
    output.write_bytes(preview_png)
    print(f"Saved: {output}")
