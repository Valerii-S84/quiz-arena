from __future__ import annotations

from datetime import datetime
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

from app.workers.tasks.tournaments_proof_card_style import (
    ARENA_ACCENT,
    ARENA_BG,
    CARD_H,
    CARD_SIZE,
    CARD_W,
    CHAMPION_BG,
    PARTICIPANT_ACCENT,
    PARTICIPANT_BG,
    PLACE_LABELS,
    draw_centered,
    draw_gradient,
    format_date,
    load_font,
    rgb,
    truncate,
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
    label, accent_hex = PLACE_LABELS.get(place, (f"PLATZ #{place}", "#FFFFFF"))
    accent = rgb(accent_hex)
    image = Image.new("RGBA", CARD_SIZE, color=rgb(CHAMPION_BG[0]) + (255,))
    draw_gradient(image, top_hex=CHAMPION_BG[0], bottom_hex=CHAMPION_BG[1])
    overlay = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    red, green, blue = accent
    overlay_draw.ellipse([-220, -220, 620, 620], fill=(red, green, blue, 26))
    overlay_draw.ellipse([500, 500, 1300, 1300], fill=(red, green, blue, 26))
    image.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(radius=24)))
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, CARD_W - 20, CARD_H - 20], outline=accent, width=2)

    draw_centered(draw, text="QUIZ ARENA", y=60, font_obj=load_font(46, bold=True), fill=accent)
    x0 = int((CARD_W - 200) / 2)
    draw.line([(x0, 132), (x0 + 200, 132)], fill=accent, width=2)
    draw_centered(draw, text=f"#{place}", y=168, font_obj=load_font(120, bold=True), fill=accent)
    draw_centered(draw, text=label, y=334, font_obj=load_font(42, bold=True), fill=accent)
    draw_centered(
        draw,
        text=truncate(tournament_name, fallback="Privates Turnier", limit=34),
        y=430,
        font_obj=load_font(32),
        fill=(255, 255, 255),
    )
    draw_centered(
        draw,
        text=truncate(player_label, fallback="Spieler", limit=20),
        y=500,
        font_obj=load_font(72, bold=True),
        fill=(255, 255, 255),
    )
    x1 = int((CARD_W - 640) / 2)
    draw.line([(x1, 636), (x1 + 640, 636)], fill=(190, 200, 215), width=2)
    draw_centered(
        draw,
        text=f"Punkte: {points}",
        y=684,
        font_obj=load_font(48, bold=True),
        fill=accent,
    )
    rounds = max(1, int(rounds_played or 0))
    draw_centered(
        draw,
        text=f"{rounds} Runden · {format_label} · {format_date(completed_at)}",
        y=898,
        font_obj=load_font(24),
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
    image = Image.new("RGB", CARD_SIZE, color=rgb(ARENA_BG[0]))
    draw_gradient(image, top_hex=ARENA_BG[0], bottom_hex=ARENA_BG[1])
    draw = ImageDraw.Draw(image)
    for y in range(0, CARD_H, 28):
        shade = 24 if (y // 28) % 2 == 0 else 30
        draw.line([(0, y), (CARD_W, y)], fill=(shade, shade, shade), width=1)
    for y in range(16, CARD_H, 40):
        for x in range(16, CARD_W, 40):
            draw.point((x, y), fill=(42, 42, 42))

    accent = rgb(ARENA_ACCENT)
    subtitle = truncate(tournament_name, fallback="IM DAILY ARENA CUP", limit=32)
    place_fill = accent if place <= 5 else (255, 255, 255)
    draw_centered(draw, text="QUIZ ARENA", y=66, font_obj=load_font(46, bold=True), fill=accent)
    draw_centered(draw, text="HEUTE", y=130, font_obj=load_font(28), fill=(150, 150, 150))
    draw_centered(
        draw, text=f"#{place}", y=210, font_obj=load_font(140, bold=True), fill=place_fill
    )
    draw_centered(draw, text=subtitle, y=416, font_obj=load_font(36), fill=(255, 255, 255))
    draw_centered(
        draw,
        text=truncate(player_label, fallback="Spieler", limit=20),
        y=510,
        font_obj=load_font(64, bold=True),
        fill=(255, 255, 255),
    )
    draw_centered(
        draw,
        text=f"Punkte: {points}",
        y=632,
        font_obj=load_font(44, bold=True),
        fill=accent,
    )
    rounds = max(1, int(rounds_played or 0))
    draw_centered(
        draw,
        text=f"{format_date(completed_at)} · {rounds} Runden · {format_label}",
        y=908,
        font_obj=load_font(24),
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
    image = Image.new("RGB", CARD_SIZE, color=rgb(PARTICIPANT_BG[0]))
    draw_gradient(image, top_hex=PARTICIPANT_BG[0], bottom_hex=PARTICIPANT_BG[1])
    draw = ImageDraw.Draw(image)
    accent = rgb(PARTICIPANT_ACCENT)

    draw_centered(
        draw, text="ICH WAR DABEI!", y=184, font_obj=load_font(56, bold=True), fill=accent
    )
    draw_centered(
        draw,
        text=truncate(tournament_name, fallback="Privates Turnier", limit=34),
        y=338,
        font_obj=load_font(36),
        fill=(255, 255, 255),
    )
    draw_centered(
        draw,
        text=truncate(player_label, fallback="Spieler", limit=20),
        y=458,
        font_obj=load_font(68, bold=True),
        fill=(255, 255, 255),
    )
    draw_centered(draw, text=f"Platz #{place}", y=624, font_obj=load_font(34), fill=(222, 222, 222))
    draw_centered(
        draw, text=format_date(completed_at), y=700, font_obj=load_font(28), fill=(190, 190, 190)
    )
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
