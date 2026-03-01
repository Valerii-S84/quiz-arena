from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageColor, ImageDraw, ImageFont

BERLIN_TZ = ZoneInfo("Europe/Berlin")
CARD_SIZE = (1080, 1080)
CARD_W, CARD_H = CARD_SIZE

CHAMPION_BG = ("#0D1B2A", "#1B2A3B")
ARENA_BG = ("#141414", "#101010")
PARTICIPANT_BG = ("#1A1A2E", "#16213E")
ARENA_ACCENT = "#39FF14"
PARTICIPANT_ACCENT = "#E94560"
PLACE_LABELS: dict[int, tuple[str, str]] = {
    1: ("GOLD", "#FFD700"),
    2: ("SILBER", "#C0C8D0"),
    3: ("BRONZE", "#CD7F32"),
}

FONT_BOLD_SEARCH_PATHS = (
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
FONT_REGULAR_SEARCH_PATHS = (
    "assets/fonts/Montserrat-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "DejaVuSans.ttf",
    "Arial.ttf",
    "arial.ttf",
)


def format_date(date_utc: datetime | None) -> str:
    resolved = date_utc or datetime.now(timezone.utc)
    return resolved.astimezone(BERLIN_TZ).strftime("%d.%m.%Y")


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_BOLD_SEARCH_PATHS if bold else FONT_REGULAR_SEARCH_PATHS:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def truncate(value: str | None, *, fallback: str, limit: int) -> str:
    resolved = (value or fallback).strip() or fallback
    return resolved if len(resolved) <= limit else f"{resolved[: limit - 3].rstrip()}..."


def rgb(color: str) -> tuple[int, int, int]:
    red, green, blue, *_ = ImageColor.getrgb(color)
    return (red, green, blue)


def draw_centered(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    y: int,
    font_obj: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    left, _, right, _ = draw.textbbox((0, 0), text=text, font=font_obj)
    draw.text((int((CARD_W - (right - left)) / 2), y), text=text, font=font_obj, fill=fill)


def draw_gradient(image: Image.Image, *, top_hex: str, bottom_hex: str) -> None:
    draw = ImageDraw.Draw(image)
    top, bottom = rgb(top_hex), rgb(bottom_hex)
    max_index = max(1, CARD_H - 1)
    for y in range(CARD_H):
        ratio = y / max_index
        draw.line(
            [(0, y), (CARD_W, y)],
            fill=(
                int(top[0] + (bottom[0] - top[0]) * ratio),
                int(top[1] + (bottom[1] - top[1]) * ratio),
                int(top[2] + (bottom[2] - top[2]) * ratio),
            ),
        )
