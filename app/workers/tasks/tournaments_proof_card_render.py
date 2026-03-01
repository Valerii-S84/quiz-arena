from __future__ import annotations
from datetime import datetime, timezone
from io import BytesIO
from zoneinfo import ZoneInfo
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont
_BERLIN_TZ = ZoneInfo("Europe/Berlin")
_CARD_SIZE = (1080, 1080)
_CARD_W, _CARD_H = _CARD_SIZE
_CHAMPION_BG = ("#0D1B2A", "#1B2A3B")
_ARENA_BG = ("#141414", "#101010")
_PARTICIPANT_BG = ("#1A1A2E", "#16213E")
_ARENA_ACCENT = "#39FF14"
_PARTICIPANT_ACCENT = "#E94560"
_PLACE_LABELS: dict[int, tuple[str, str]] = {
    1: ("GOLD", "#FFD700"),
    2: ("SILBER", "#C0C8D0"),
    3: ("BRONZE", "#CD7F32"),
}
_FONT_BOLD_SEARCH_PATHS = (
    "assets/fonts/Bebas-Neue.ttf",
    "assets/fonts/Montserrat-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "DejaVuSans-Bold.ttf",
    "Arial Bold.ttf",
    "arialbd.ttf",
)
_FONT_REGULAR_SEARCH_PATHS = (
    "assets/fonts/Montserrat-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "DejaVuSans.ttf",
    "Arial.ttf",
    "arial.ttf",
)
def _format_date(date_utc: datetime | None) -> str:
    resolved = date_utc or datetime.now(timezone.utc)
    return resolved.astimezone(_BERLIN_TZ).strftime("%d.%m.%Y")
def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_BOLD_SEARCH_PATHS if bold else _FONT_REGULAR_SEARCH_PATHS:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()
def _truncate(value: str | None, *, fallback: str, limit: int) -> str:
    resolved = (value or fallback).strip() or fallback
    return resolved if len(resolved) <= limit else f"{resolved[: limit - 3].rstrip()}..."
def _rgb(color: str) -> tuple[int, int, int]:
    red, green, blue, *_ = ImageColor.getrgb(color)
    return (red, green, blue)
def _draw_centered(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    y: int,
    font_obj: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    left, _, right, _ = draw.textbbox((0, 0), text=text, font=font_obj)
    draw.text((int((_CARD_W - (right - left)) / 2), y), text=text, font=font_obj, fill=fill)
def _draw_gradient(image: Image.Image, *, top_hex: str, bottom_hex: str) -> None:
    draw = ImageDraw.Draw(image)
    top, bottom = _rgb(top_hex), _rgb(bottom_hex)
    max_index = max(1, _CARD_H - 1)
    for y in range(_CARD_H):
        ratio = y / max_index
        draw.line(
            [(0, y), (_CARD_W, y)],
            fill=(
                int(top[0] + (bottom[0] - top[0]) * ratio),
                int(top[1] + (bottom[1] - top[1]) * ratio),
                int(top[2] + (bottom[2] - top[2]) * ratio),
            ),
        )
def _render_champion(
    *,
    player_label: str,
    place: int,
    points: str,
    format_label: str,
    completed_at: datetime | None,
    tournament_name: str | None,
    rounds_played: int | None,
) -> Image.Image:
    label, accent_hex = _PLACE_LABELS.get(place, (f"PLATZ #{place}", "#FFFFFF"))
    accent = _rgb(accent_hex)
    image = Image.new("RGBA", _CARD_SIZE, color=_rgb(_CHAMPION_BG[0]) + (255,))
    _draw_gradient(image, top_hex=_CHAMPION_BG[0], bottom_hex=_CHAMPION_BG[1])
    overlay = Image.new("RGBA", _CARD_SIZE, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    r, g, b = accent
    overlay_draw.ellipse([-220, -220, 620, 620], fill=(r, g, b, 26))
    overlay_draw.ellipse([500, 500, 1300, 1300], fill=(r, g, b, 26))
    image.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(radius=24)))
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, _CARD_W - 20, _CARD_H - 20], outline=accent, width=2)
    _draw_centered(draw, text="QUIZ ARENA", y=60, font_obj=_load_font(46, bold=True), fill=accent)
    x0 = int((_CARD_W - 200) / 2)
    draw.line([(x0, 132), (x0 + 200, 132)], fill=accent, width=2)
    _draw_centered(draw, text=f"#{place}", y=168, font_obj=_load_font(120, bold=True), fill=accent)
    _draw_centered(draw, text=label, y=334, font_obj=_load_font(42, bold=True), fill=accent)
    _draw_centered(
        draw,
        text=_truncate(tournament_name, fallback="Privates Turnier", limit=34),
        y=430,
        font_obj=_load_font(32),
        fill=(255, 255, 255),
    )
    _draw_centered(
        draw,
        text=_truncate(player_label, fallback="Spieler", limit=20),
        y=500,
        font_obj=_load_font(72, bold=True),
        fill=(255, 255, 255),
    )
    x1 = int((_CARD_W - 640) / 2)
    draw.line([(x1, 636), (x1 + 640, 636)], fill=(190, 200, 215), width=2)
    _draw_centered(
        draw,
        text=f"Punkte: {points}",
        y=684,
        font_obj=_load_font(48, bold=True),
        fill=accent,
    )
    rounds = max(1, int(rounds_played or 0))
    _draw_centered(
        draw,
        text=f"{rounds} Runden · {format_label} · {_format_date(completed_at)}",
        y=898,
        font_obj=_load_font(24),
        fill=(168, 176, 188),
    )
    return image.convert("RGB")
def _render_arena(
    *,
    player_label: str,
    place: int,
    points: str,
    format_label: str,
    completed_at: datetime | None,
    tournament_name: str | None,
    rounds_played: int | None,
) -> Image.Image:
    image = Image.new("RGB", _CARD_SIZE, color=_rgb(_ARENA_BG[0]))
    _draw_gradient(image, top_hex=_ARENA_BG[0], bottom_hex=_ARENA_BG[1])
    draw = ImageDraw.Draw(image)
    for y in range(0, _CARD_H, 28):
        shade = 24 if (y // 28) % 2 == 0 else 30
        draw.line([(0, y), (_CARD_W, y)], fill=(shade, shade, shade), width=1)
    for y in range(16, _CARD_H, 40):
        for x in range(16, _CARD_W, 40):
            draw.point((x, y), fill=(42, 42, 42))
    accent = _rgb(_ARENA_ACCENT)
    subtitle = _truncate(tournament_name, fallback="IM DAILY ARENA CUP", limit=32)
    place_fill = accent if place <= 5 else (255, 255, 255)
    _draw_centered(draw, text="QUIZ ARENA", y=66, font_obj=_load_font(46, bold=True), fill=accent)
    _draw_centered(draw, text="HEUTE", y=130, font_obj=_load_font(28), fill=(150, 150, 150))
    _draw_centered(draw, text=f"#{place}", y=210, font_obj=_load_font(140, bold=True), fill=place_fill)
    _draw_centered(draw, text=subtitle, y=416, font_obj=_load_font(36), fill=(255, 255, 255))
    _draw_centered(
        draw,
        text=_truncate(player_label, fallback="Spieler", limit=20),
        y=510,
        font_obj=_load_font(64, bold=True),
        fill=(255, 255, 255),
    )
    _draw_centered(draw, text=f"Punkte: {points}", y=632, font_obj=_load_font(44, bold=True), fill=accent)
    rounds = max(1, int(rounds_played or 0))
    _draw_centered(
        draw,
        text=f"{_format_date(completed_at)} · {rounds} Runden · {format_label}",
        y=908,
        font_obj=_load_font(24),
        fill=(170, 170, 170),
    )
    return image
def _render_participant(
    *,
    player_label: str,
    place: int,
    completed_at: datetime | None,
    tournament_name: str | None,
) -> Image.Image:
    image = Image.new("RGB", _CARD_SIZE, color=_rgb(_PARTICIPANT_BG[0]))
    _draw_gradient(image, top_hex=_PARTICIPANT_BG[0], bottom_hex=_PARTICIPANT_BG[1])
    draw = ImageDraw.Draw(image)
    accent = _rgb(_PARTICIPANT_ACCENT)
    _draw_centered(draw, text="ICH WAR DABEI!", y=184, font_obj=_load_font(56, bold=True), fill=accent)
    _draw_centered(
        draw,
        text=_truncate(tournament_name, fallback="Privates Turnier", limit=34),
        y=338,
        font_obj=_load_font(36),
        fill=(255, 255, 255),
    )
    _draw_centered(
        draw,
        text=_truncate(player_label, fallback="Spieler", limit=20),
        y=458,
        font_obj=_load_font(68, bold=True),
        fill=(255, 255, 255),
    )
    _draw_centered(draw, text=f"Platz #{place}", y=624, font_obj=_load_font(34), fill=(222, 222, 222))
    _draw_centered(draw, text=_format_date(completed_at), y=700, font_obj=_load_font(28), fill=(190, 190, 190))
    return image
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
    if place <= 3:
        image = _render_champion(
            player_label=player_label,
            place=place,
            points=points,
            format_label=format_label,
            completed_at=completed_at,
            tournament_name=tournament_name,
            rounds_played=rounds_played,
        )
    elif place <= 10:
        image = _render_arena(
            player_label=player_label,
            place=place,
            points=points,
            format_label=format_label,
            completed_at=completed_at,
            tournament_name=tournament_name,
            rounds_played=rounds_played,
        )
    else:
        image = _render_participant(
            player_label=player_label,
            place=place,
            completed_at=completed_at,
            tournament_name=tournament_name,
        )
    buffer = BytesIO()
    image.save(buffer, format="PNG", compress_level=1)
    return buffer.getvalue()
