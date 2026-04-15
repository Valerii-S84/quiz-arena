from __future__ import annotations

from PIL import Image, ImageDraw

from app.workers.tasks.friend_challenges_proof_card_style import (
    BRAND,
    CARD_SIZE,
    TEXT_MAIN,
    TEXT_MUTED,
    TITLE,
    center_x,
    draw_fade_line,
    draw_spaced_text,
    font,
)


def draw_brand_header(
    *, image: Image.Image, draw: ImageDraw.ImageDraw, logo: Image.Image | None
) -> None:
    alpha_extrema: object | None = None
    if logo is not None and "A" in logo.getbands():
        alpha_extrema = logo.getchannel("A").getextrema()
    alpha_min = 255
    if isinstance(alpha_extrema, tuple) and alpha_extrema:
        first_item = alpha_extrema[0]
        alpha_min = int(first_item[0] if isinstance(first_item, tuple) else first_item)
    elif isinstance(alpha_extrema, (int, float)):
        alpha_min = int(alpha_extrema)

    if logo is not None and "A" in logo.getbands() and alpha_min < 250:
        logo_height = 120
        logo_width = max(1, int((logo.width / max(1, logo.height)) * logo_height))
        if logo_width > 760:
            logo_width = 760
            logo_height = max(1, int((logo.height / max(1, logo.width)) * logo_width))
        logo_resized = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
        image.alpha_composite(logo_resized, (int((CARD_SIZE - logo_width) / 2), 54))
        return

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


def draw_title(*, draw: ImageDraw.ImageDraw) -> None:
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


def draw_meta(
    *,
    draw: ImageDraw.ImageDraw,
    total_rounds: int,
    date_text: str,
) -> None:
    meta_font = font(size=44, bold=False)
    draw.text(
        (center_x(draw=draw, text=f"FORMAT: {total_rounds} FRAGEN", font_obj=meta_font), 906),
        f"FORMAT: {total_rounds} FRAGEN",
        font=meta_font,
        fill=TEXT_MUTED,
    )
    draw.text(
        (center_x(draw=draw, text=f"DATUM: {date_text}", font_obj=meta_font), 958),
        f"DATUM: {date_text}",
        font=meta_font,
        fill=TEXT_MUTED,
    )
    draw_fade_line(draw, y=1016, width=680, color=(255, 215, 0), alpha=180)


__all__ = ["draw_brand_header", "draw_meta", "draw_title"]
