from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import random
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

_CARD_SIZE = 1080
_BERLIN_TZ = ZoneInfo("Europe/Berlin")
_BG_CENTER = (15, 15, 26)
_BG_EDGE = (8, 8, 8)
_TEXT_MAIN = (244, 247, 255, 255)
_TEXT_MUTED = (136, 136, 136, 255)
_GOLD = (255, 215, 0, 255)
_SILVER = (192, 192, 192, 255)
_LOSER_GRAY = (136, 136, 136, 255)
_PANEL_DARK = (17, 17, 17, 235)
_PANEL_GOLD = (26, 21, 0, 235)
_PANEL_SILVER = (18, 18, 18, 235)
_BRAND = "QUIZ ARENA"
_TITLE = "DUELL ERGEBNIS"


_FontType = ImageFont.FreeTypeFont | ImageFont.ImageFont


def _font(*, size: int, bold: bool) -> _FontType:
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


def _center_x(*, draw: ImageDraw.ImageDraw, text: str, font: _FontType, tracking: int = 0) -> int:
    width = _text_width(draw=draw, text=text, font=font, tracking=tracking)
    return int((_CARD_SIZE - width) / 2)


def _text_width(*, draw: ImageDraw.ImageDraw, text: str, font: _FontType, tracking: int = 0) -> int:
    if not text:
        return 0
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return int((right - left) + tracking * max(0, len(text) - 1))


def _center_x_in_box(
    *,
    draw: ImageDraw.ImageDraw,
    text: str,
    font: _FontType,
    left: int,
    right: int,
) -> int:
    text_width = _text_width(draw=draw, text=text, font=font)
    return int(left + ((right - left - text_width) / 2))


def _fit_name_font(
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
        trial_font = _font(size=size, bold=bold)
        if _text_width(draw=draw, text=clean, font=trial_font) <= max_width:
            return clean, trial_font
    return clean, _font(size=min_size, bold=bold)


def _draw_spaced_text(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    x: int,
    y: int,
    font: _FontType,
    fill: tuple[int, int, int, int] | tuple[int, int, int],
    tracking: int = 0,
) -> None:
    cursor_x = x
    for char in text:
        draw.text((cursor_x, y), char, font=font, fill=fill)
        ch_width = int(draw.textbbox((0, 0), char, font=font)[2])
        cursor_x += ch_width + tracking


def _draw_radial_background() -> Image.Image:
    image = Image.new("RGBA", (_CARD_SIZE, _CARD_SIZE), _BG_EDGE + (255,))
    pixels = image.load()
    if pixels is None:
        return image
    center_x = _CARD_SIZE // 2
    center_y = int(_CARD_SIZE * 0.45)
    max_distance = ((center_x**2) + (center_y**2)) ** 0.5
    rng = random.Random(42)

    for y in range(_CARD_SIZE):
        for x in range(_CARD_SIZE):
            distance = (((x - center_x) ** 2) + ((y - center_y) ** 2)) ** 0.5
            ratio = min(1.0, max(0.0, distance / max_distance))
            base_r = int(_BG_CENTER[0] * (1.0 - ratio) + _BG_EDGE[0] * ratio)
            base_g = int(_BG_CENTER[1] * (1.0 - ratio) + _BG_EDGE[1] * ratio)
            base_b = int(_BG_CENTER[2] * (1.0 - ratio) + _BG_EDGE[2] * ratio)
            noise = rng.randint(-5, 5)
            pixels[x, y] = (
                max(0, min(255, base_r + noise)),
                max(0, min(255, base_g + noise)),
                max(0, min(255, base_b + noise)),
                255,
            )

    overlay = Image.new("RGBA", (_CARD_SIZE, _CARD_SIZE), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.ellipse((700, -120, 1260, 420), fill=(255, 255, 255, 12))
    overlay_draw.arc((-220, 760, 360, 1340), start=240, end=360, fill=(30, 30, 58, 102), width=4)
    overlay_draw.arc((760, -220, 1360, 360), start=90, end=230, fill=(32, 32, 58, 102), width=4)
    image.alpha_composite(overlay)
    return image


def _format_date(date_utc: datetime | None) -> str:
    resolved = date_utc or datetime.now(timezone.utc)
    return resolved.astimezone(_BERLIN_TZ).strftime("%d.%m.%Y")


def _winner_side(*, creator_score: int, opponent_score: int) -> str | None:
    if creator_score > opponent_score:
        return "creator"
    if opponent_score > creator_score:
        return "opponent"
    return None


def _draw_fade_line(
    draw: ImageDraw.ImageDraw, *, y: int, width: int, color: tuple[int, int, int], alpha: int = 210
) -> None:
    left = int((_CARD_SIZE - width) / 2)
    for idx in range(width):
        ratio = idx / max(1, width - 1)
        center_fade = 1.0 - abs((2.0 * ratio) - 1.0)
        current_alpha = int(alpha * center_fade)
        draw.line(
            ((left + idx, y), (left + idx, y + 1)),
            fill=(color[0], color[1], color[2], current_alpha),
        )


def _load_logo() -> Image.Image | None:
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


def render_duel_proof_card_png(
    *,
    creator_name: str,
    opponent_name: str,
    creator_score: int,
    opponent_score: int,
    total_rounds: int,
    completed_at: datetime | None,
) -> bytes:
    image = _draw_radial_background()
    draw = ImageDraw.Draw(image)

    logo = _load_logo()
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
        image.alpha_composite(logo_resized, ((int((_CARD_SIZE - logo_width) / 2)), 54))
    else:
        brand_font = _font(size=76, bold=True)
        brand_x = _center_x(draw=draw, text=_BRAND, font=brand_font, tracking=6)
        _draw_spaced_text(
            draw,
            text=_BRAND,
            x=brand_x + 2,
            y=76,
            font=brand_font,
            fill=(0, 0, 0, 160),
            tracking=6,
        )
        _draw_spaced_text(
            draw,
            text=_BRAND,
            x=brand_x,
            y=74,
            font=brand_font,
            fill=(224, 229, 238, 255),
            tracking=6,
        )

    title_font = _font(size=84, bold=True)
    title_x = _center_x(draw=draw, text=_TITLE, font=title_font, tracking=5)
    _draw_spaced_text(
        draw,
        text=_TITLE,
        x=title_x + 2,
        y=228,
        font=title_font,
        fill=(0, 0, 0, 153),
        tracking=5,
    )
    _draw_spaced_text(
        draw,
        text=_TITLE,
        x=title_x,
        y=226,
        font=title_font,
        fill=_TEXT_MAIN,
        tracking=5,
    )

    panel_top = 362
    panel_height = 226
    left_panel = (64, panel_top, 508, panel_top + panel_height)
    right_panel = (572, panel_top, 1016, panel_top + panel_height)

    winner = _winner_side(creator_score=creator_score, opponent_score=opponent_score)
    if winner == "creator":
        left_border, right_border = _GOLD, (102, 102, 102, 255)
        left_fill, right_fill = _PANEL_GOLD, _PANEL_DARK
        left_name_color, right_name_color = _GOLD, _LOSER_GRAY
        left_label = creator_name
        right_label = opponent_name
        left_score_color, right_score_color = _GOLD, _LOSER_GRAY
    elif winner == "opponent":
        left_border, right_border = (102, 102, 102, 255), _GOLD
        left_fill, right_fill = _PANEL_DARK, _PANEL_GOLD
        left_name_color, right_name_color = _LOSER_GRAY, _GOLD
        left_label = creator_name
        right_label = opponent_name
        left_score_color, right_score_color = _LOSER_GRAY, _GOLD
    else:
        left_border = right_border = _SILVER
        left_fill = right_fill = _PANEL_SILVER
        left_name_color = right_name_color = _SILVER
        left_label = creator_name
        right_label = opponent_name
        left_score_color = right_score_color = _SILVER

    draw.rounded_rectangle(left_panel, radius=34, fill=left_fill, outline=left_border, width=8)
    draw.rounded_rectangle(right_panel, radius=34, fill=right_fill, outline=right_border, width=8)

    left_name, left_font = _fit_name_font(
        name=left_label,
        draw=draw,
        bold=True,
        max_width=390,
    )
    right_name, right_font = _fit_name_font(
        name=right_label,
        draw=draw,
        bold=True,
        max_width=390,
    )
    draw.text(
        (
            _center_x_in_box(
                draw=draw,
                text=left_name,
                font=left_font,
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
            _center_x_in_box(
                draw=draw,
                text=right_name,
                font=right_font,
                left=right_panel[0],
                right=right_panel[2],
            ),
            446,
        ),
        right_name,
        font=right_font,
        fill=right_name_color,
    )

    _draw_fade_line(draw, y=618, width=600, color=(255, 215, 0), alpha=200)

    score_font = _font(size=210, bold=True)
    left_score = str(creator_score)
    right_score = str(opponent_score)
    colon = " : "
    left_width = _text_width(draw=draw, text=left_score, font=score_font)
    colon_width = _text_width(draw=draw, text=colon, font=score_font)
    right_width = _text_width(draw=draw, text=right_score, font=score_font)
    score_x = int((_CARD_SIZE - (left_width + colon_width + right_width)) / 2)
    score_y = 652
    draw.text((score_x, score_y), left_score, font=score_font, fill=left_score_color)
    draw.text((score_x + left_width, score_y), colon, font=score_font, fill=(255, 255, 255, 255))
    draw.text(
        (score_x + left_width + colon_width, score_y),
        right_score,
        font=score_font,
        fill=right_score_color,
    )

    meta_font = _font(size=44, bold=False)
    format_text = f"FORMAT: {max(1, int(total_rounds))} FRAGEN"
    date_text = f"DATUM: {_format_date(completed_at)}"
    draw.text(
        (_center_x(draw=draw, text=format_text, font=meta_font), 906),
        format_text,
        font=meta_font,
        fill=_TEXT_MUTED,
    )
    draw.text(
        (_center_x(draw=draw, text=date_text, font=meta_font), 958),
        date_text,
        font=meta_font,
        fill=_TEXT_MUTED,
    )
    _draw_fade_line(draw, y=1016, width=680, color=(255, 215, 0), alpha=180)

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
