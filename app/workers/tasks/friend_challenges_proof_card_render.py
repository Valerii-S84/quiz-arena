from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

_CARD_SIZE = 1080
_BERLIN_TZ = ZoneInfo("Europe/Berlin")
_BG_TOP = (10, 14, 24)
_BG_BOTTOM = (20, 26, 44)
_TEXT_MAIN = (244, 247, 255)
_TEXT_MUTED = (154, 168, 196)
_ACCENT = (255, 195, 72)
_WINNER_BORDER = (255, 195, 72)
_LOSER_BORDER = (62, 73, 99)
_PANEL_FILL = (17, 23, 38)
_DECO = (33, 42, 66)
_BRAND = "QUIZ ARENA"
_TITLE = "DUELL ERGEBNIS"


_FontType = ImageFont.FreeTypeFont | ImageFont.ImageFont


def _font(*, size: int, bold: bool) -> _FontType:
    candidates: list[Path]
    if bold:
        candidates = [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ]
    else:
        candidates = [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _center_x(*, draw: ImageDraw.ImageDraw, text: str, font: _FontType) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return int((_CARD_SIZE - (right - left)) / 2)


def _center_x_in_box(
    *,
    draw: ImageDraw.ImageDraw,
    text: str,
    font: _FontType,
    left: int,
    right: int,
) -> int:
    text_box = draw.textbbox((0, 0), text, font=font)
    text_width = text_box[2] - text_box[0]
    return int(left + ((right - left - text_width) / 2))


def _fit_name(*, name: str, draw: ImageDraw.ImageDraw, font: _FontType, max_width: int) -> str:
    clean = (name or "Spieler").strip() or "Spieler"
    if draw.textbbox((0, 0), clean, font=font)[2] <= max_width:
        return clean
    clipped = clean
    while clipped and draw.textbbox((0, 0), f"{clipped}...", font=font)[2] > max_width:
        clipped = clipped[:-1]
    return f"{clipped}..." if clipped else "Spieler"


def _draw_gradient(draw: ImageDraw.ImageDraw) -> None:
    for y in range(_CARD_SIZE):
        ratio = y / (_CARD_SIZE - 1)
        color = tuple(
            int(_BG_TOP[idx] * (1.0 - ratio) + _BG_BOTTOM[idx] * ratio) for idx in range(3)
        )
        draw.line(((0, y), (_CARD_SIZE, y)), fill=color)


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
    image = Image.new("RGB", (_CARD_SIZE, _CARD_SIZE), _BG_TOP)
    draw = ImageDraw.Draw(image)
    _draw_gradient(draw)

    draw.ellipse((760, -120, 1240, 360), fill=_DECO)
    draw.ellipse((-140, 760, 280, 1180), fill=_DECO)

    brand_font = _font(size=54, bold=True)
    qa_font = _font(size=44, bold=True)
    draw.rounded_rectangle((74, 66, 170, 162), radius=24, fill=_ACCENT)
    draw.text((101, 87), "QA", font=qa_font, fill=(25, 25, 25))
    draw.text((196, 83), _BRAND, font=brand_font, fill=_TEXT_MAIN)

    title_font = _font(size=74, bold=True)
    draw.text(
        (_center_x(draw=draw, text=_TITLE, font=title_font), 228),
        _TITLE,
        font=title_font,
        fill=_TEXT_MAIN,
    )

    panel_top = 392
    panel_height = 226
    left_panel = (74, panel_top, 498, panel_top + panel_height)
    right_panel = (582, panel_top, 1006, panel_top + panel_height)

    winner = _winner_side(creator_score=creator_score, opponent_score=opponent_score)
    left_border = _WINNER_BORDER if winner == "creator" else _LOSER_BORDER
    right_border = _WINNER_BORDER if winner == "opponent" else _LOSER_BORDER
    draw.rounded_rectangle(left_panel, radius=34, fill=_PANEL_FILL, outline=left_border, width=8)
    draw.rounded_rectangle(right_panel, radius=34, fill=_PANEL_FILL, outline=right_border, width=8)

    name_font = _font(size=56, bold=True)
    name_max_width = 360
    left_name = _fit_name(
        name=creator_name,
        draw=draw,
        font=name_font,
        max_width=name_max_width,
    )
    right_name = _fit_name(
        name=opponent_name,
        draw=draw,
        font=name_font,
        max_width=name_max_width,
    )
    left_name_color = _ACCENT if winner == "creator" else _TEXT_MAIN
    right_name_color = _ACCENT if winner == "opponent" else _TEXT_MAIN
    draw.text(
        (
            _center_x_in_box(
                draw=draw,
                text=left_name,
                font=name_font,
                left=left_panel[0],
                right=left_panel[2],
            ),
            472,
        ),
        left_name,
        font=name_font,
        fill=left_name_color,
    )
    draw.text(
        (
            _center_x_in_box(
                draw=draw,
                text=right_name,
                font=name_font,
                left=right_panel[0],
                right=right_panel[2],
            ),
            472,
        ),
        right_name,
        font=name_font,
        fill=right_name_color,
    )

    score_font = _font(size=182, bold=True)
    score_text = f"{creator_score} : {opponent_score}"
    draw.text(
        (_center_x(draw=draw, text=score_text, font=score_font), 652),
        score_text,
        font=score_font,
        fill=_TEXT_MAIN,
    )

    meta_font = _font(size=44, bold=False)
    format_text = f"FORMAT: {max(1, int(total_rounds))} FRAGEN"
    date_text = f"DATUM: {_format_date(completed_at)}"
    draw.text(
        (_center_x(draw=draw, text=format_text, font=meta_font), 900),
        format_text,
        font=meta_font,
        fill=_TEXT_MUTED,
    )
    draw.text(
        (_center_x(draw=draw, text=date_text, font=meta_font), 952),
        date_text,
        font=meta_font,
        fill=_TEXT_MUTED,
    )

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
