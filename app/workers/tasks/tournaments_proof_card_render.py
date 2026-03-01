from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

_BERLIN_TZ = ZoneInfo("Europe/Berlin")
_CARD_SIZE = (1080, 1080)

_TOP_COLORS: dict[int, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    1: ((255, 212, 96), (146, 97, 26)),
    2: ((214, 220, 230), (100, 112, 130)),
    3: ((224, 171, 125), (128, 79, 44)),
}
_DEFAULT_COLORS = ((112, 167, 255), (37, 78, 142))


def _resolve_colors(place: int) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    return _TOP_COLORS.get(place, _DEFAULT_COLORS)


def _format_date(date_utc: datetime | None) -> str:
    resolved = date_utc or datetime.now(timezone.utc)
    return resolved.astimezone(_BERLIN_TZ).strftime("%d.%m.%Y")


def _medal_symbol(place: int) -> str:
    if place == 1:
        return "🥇"
    if place == 2:
        return "🥈"
    if place == 3:
        return "🥉"
    return "🏅"


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_names = (
        ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf")
        if bold
        else ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf")
    )
    for name in font_names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _truncate_tournament_name(name: str | None) -> str:
    resolved = (name or "Privates Turnier").strip() or "Privates Turnier"
    if len(resolved) <= 30:
        return resolved
    return f"{resolved[:27].rstrip()}..."


def _draw_gradient_background(
    *,
    image: Image.Image,
    top_color: tuple[int, int, int],
    bottom_color: tuple[int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    width, height = _CARD_SIZE
    max_index = max(1, height - 1)
    for y in range(height):
        ratio = y / max_index
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    y: int,
    font_obj: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    width = draw.textbbox((0, 0), text=text, font=font_obj)[2]
    x = int((_CARD_SIZE[0] - width) / 2)
    draw.text((x, y), text=text, font=font_obj, fill=fill)


def render_tournament_proof_card_png(
    *,
    player_label: str,
    place: int,
    points: str,
    format_label: str,
    completed_at: datetime | None,
    tournament_name: str | None = None,
    rounds_played: int | None = None,
) -> bytes:
    image = Image.new("RGB", _CARD_SIZE, color=(0, 0, 0))
    top_color, bottom_color = _resolve_colors(place)
    _draw_gradient_background(image=image, top_color=top_color, bottom_color=bottom_color)
    draw = ImageDraw.Draw(image)

    title_font = _load_font(64, bold=True)
    subtitle_font = _load_font(42, bold=False)
    player_font = _load_font(86, bold=True)
    score_font = _load_font(74, bold=True)
    meta_font = _load_font(38, bold=False)

    _draw_centered(draw, text="QUIZ ARENA", y=92, font_obj=title_font, fill=(255, 255, 255))
    _draw_centered(
        draw,
        text="TURNIER PROOF CARD",
        y=180,
        font_obj=subtitle_font,
        fill=(245, 245, 245),
    )
    _draw_centered(
        draw,
        text=f"{_medal_symbol(place)} PLATZ #{place}",
        y=338,
        font_obj=player_font,
        fill=(255, 255, 255),
    )
    _draw_centered(
        draw,
        text=_truncate_tournament_name(tournament_name),
        y=420,
        font_obj=subtitle_font,
        fill=(245, 245, 245),
    )
    _draw_centered(
        draw,
        text=player_label,
        y=520,
        font_obj=player_font,
        fill=(255, 255, 255),
    )
    _draw_centered(
        draw,
        text=f"Punkte: {points}",
        y=670,
        font_obj=score_font,
        fill=(255, 255, 255),
    )
    _draw_centered(
        draw,
        text=f"Format: {format_label}",
        y=780,
        font_obj=meta_font,
        fill=(242, 242, 242),
    )
    _draw_centered(
        draw,
        text=f"{max(1, int(rounds_played or 0))} Runden gespielt",
        y=840,
        font_obj=meta_font,
        fill=(242, 242, 242),
    )
    _draw_centered(
        draw,
        text=f"Datum: {_format_date(completed_at)}",
        y=900,
        font_obj=meta_font,
        fill=(242, 242, 242),
    )

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
