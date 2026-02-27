from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CARD_SIZE = 1080
BG_CENTER = (15, 15, 26)
BG_EDGE = (8, 8, 8)
TEXT_MAIN = (244, 247, 255, 255)
TEXT_MUTED = (136, 136, 136, 255)
GOLD = (255, 215, 0, 255)
SILVER = (192, 192, 192, 255)
LOSER_GRAY = (136, 136, 136, 255)
PANEL_DARK = (17, 17, 17, 235)
PANEL_GOLD = (26, 21, 0, 235)
PANEL_SILVER = (18, 18, 18, 235)
BRAND = "QUIZ ARENA"
TITLE = "DUELL ERGEBNIS"


_FontType = ImageFont.FreeTypeFont | ImageFont.ImageFont


def font(*, size: int, bold: bool) -> _FontType:
    candidates = [
        Path("/usr/share/fonts/truetype/inter/Inter-Bold.ttf")
        if bold
        else Path("/usr/share/fonts/truetype/inter/Inter-Regular.ttf"),
        Path("/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Bold.ttf")
        if bold
        else Path("/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        if bold
        else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")
        if bold
        else Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def text_width(*, draw: ImageDraw.ImageDraw, text: str, font_obj: _FontType, tracking: int = 0) -> int:
    if not text:
        return 0
    left, _, right, _ = draw.textbbox((0, 0), text, font=font_obj)
    return int((right - left) + tracking * max(0, len(text) - 1))


def center_x(*, draw: ImageDraw.ImageDraw, text: str, font_obj: _FontType, tracking: int = 0) -> int:
    width = text_width(draw=draw, text=text, font_obj=font_obj, tracking=tracking)
    return int((CARD_SIZE - width) / 2)


def center_x_in_box(
    *,
    draw: ImageDraw.ImageDraw,
    text: str,
    font_obj: _FontType,
    left: int,
    right: int,
) -> int:
    width = text_width(draw=draw, text=text, font_obj=font_obj)
    return int(left + ((right - left - width) / 2))


def fit_name_font(
    *,
    draw: ImageDraw.ImageDraw,
    name: str,
    bold: bool,
    max_width: int,
    max_size: int = 60,
    min_size: int = 32,
) -> tuple[str, _FontType]:
    clean = (name or "Spieler").strip() or "Spieler"
    for size in range(max_size, min_size - 1, -2):
        trial_font = font(size=size, bold=bold)
        if text_width(draw=draw, text=clean, font_obj=trial_font) <= max_width:
            return clean, trial_font
    return clean, font(size=min_size, bold=bold)


def draw_spaced_text(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    x: int,
    y: int,
    font_obj: _FontType,
    fill: tuple[int, int, int, int] | tuple[int, int, int],
    tracking: int = 0,
) -> None:
    cursor_x = x
    for char in text:
        draw.text((cursor_x, y), char, font=font_obj, fill=fill)
        ch_width = int(draw.textbbox((0, 0), char, font=font_obj)[2])
        cursor_x += ch_width + tracking


def draw_radial_background() -> Image.Image:
    image = Image.new("RGBA", (CARD_SIZE, CARD_SIZE), BG_EDGE + (255,))
    pixels = image.load()
    if pixels is None:
        return image
    center_x_px = CARD_SIZE // 2
    center_y_px = int(CARD_SIZE * 0.45)
    max_distance = ((center_x_px**2) + (center_y_px**2)) ** 0.5
    rng = random.Random(42)

    for y in range(CARD_SIZE):
        for x in range(CARD_SIZE):
            distance = (((x - center_x_px) ** 2) + ((y - center_y_px) ** 2)) ** 0.5
            ratio = min(1.0, max(0.0, distance / max_distance))
            base_r = int(BG_CENTER[0] * (1.0 - ratio) + BG_EDGE[0] * ratio)
            base_g = int(BG_CENTER[1] * (1.0 - ratio) + BG_EDGE[1] * ratio)
            base_b = int(BG_CENTER[2] * (1.0 - ratio) + BG_EDGE[2] * ratio)
            noise = rng.randint(-5, 5)
            pixels[x, y] = (
                max(0, min(255, base_r + noise)),
                max(0, min(255, base_g + noise)),
                max(0, min(255, base_b + noise)),
                255,
            )

    overlay = Image.new("RGBA", (CARD_SIZE, CARD_SIZE), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.ellipse((700, -120, 1260, 420), fill=(255, 255, 255, 12))
    overlay_draw.arc((-220, 760, 360, 1340), start=240, end=360, fill=(30, 30, 58, 102), width=4)
    overlay_draw.arc((760, -220, 1360, 360), start=90, end=230, fill=(32, 32, 58, 102), width=4)
    image.alpha_composite(overlay)
    return image


def draw_fade_line(
    draw: ImageDraw.ImageDraw, *, y: int, width: int, color: tuple[int, int, int], alpha: int = 210
) -> None:
    left = int((CARD_SIZE - width) / 2)
    for idx in range(width):
        ratio = idx / max(1, width - 1)
        center_fade = 1.0 - abs((2.0 * ratio) - 1.0)
        current_alpha = int(alpha * center_fade)
        draw.line(
            ((left + idx, y), (left + idx, y + 1)),
            fill=(color[0], color[1], color[2], current_alpha),
        )


def load_logo() -> Image.Image | None:
    foto_dir = Path(__file__).resolve().parents[3] / "foto"
    if not foto_dir.exists():
        return None
    png_files = sorted(foto_dir.glob("*.png"))
    chosen = next((item for item in png_files if "18_11_24" in item.name), None)
    if chosen is None:
        chosen = next((item for item in png_files if "chatgpt image" in item.name.lower()), None)
    if chosen is None:
        return None
    try:
        return Image.open(chosen).convert("RGBA")
    except Exception:
        return None
