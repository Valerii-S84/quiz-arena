from __future__ import annotations

from dataclasses import dataclass

from PIL import ImageDraw

from app.workers.tasks.friend_challenges_proof_card_style import (
    CARD_SIZE,
    GOLD,
    LOSER_GRAY,
    PANEL_DARK,
    PANEL_GOLD,
    PANEL_SILVER,
    SILVER,
    center_x_in_box,
    draw_fade_line,
    fit_name_font,
    font,
    text_width,
)


@dataclass(frozen=True, slots=True)
class DuelPanelTheme:
    left_border: tuple[int, int, int, int]
    right_border: tuple[int, int, int, int]
    left_fill: tuple[int, int, int, int]
    right_fill: tuple[int, int, int, int]
    left_name_color: tuple[int, int, int, int]
    right_name_color: tuple[int, int, int, int]
    left_score_color: tuple[int, int, int, int]
    right_score_color: tuple[int, int, int, int]


def build_panel_theme(*, winner: str | None) -> DuelPanelTheme:
    if winner == "creator":
        return DuelPanelTheme(
            left_border=GOLD,
            right_border=(102, 102, 102, 255),
            left_fill=PANEL_GOLD,
            right_fill=PANEL_DARK,
            left_name_color=GOLD,
            right_name_color=LOSER_GRAY,
            left_score_color=GOLD,
            right_score_color=LOSER_GRAY,
        )
    if winner == "opponent":
        return DuelPanelTheme(
            left_border=(102, 102, 102, 255),
            right_border=GOLD,
            left_fill=PANEL_DARK,
            right_fill=PANEL_GOLD,
            left_name_color=LOSER_GRAY,
            right_name_color=GOLD,
            left_score_color=LOSER_GRAY,
            right_score_color=GOLD,
        )
    return DuelPanelTheme(
        left_border=SILVER,
        right_border=SILVER,
        left_fill=PANEL_SILVER,
        right_fill=PANEL_SILVER,
        left_name_color=SILVER,
        right_name_color=SILVER,
        left_score_color=SILVER,
        right_score_color=SILVER,
    )


def draw_name_panels(
    *,
    draw: ImageDraw.ImageDraw,
    creator_name: str,
    opponent_name: str,
    theme: DuelPanelTheme,
) -> None:
    panel_top = 362
    panel_height = 226
    left_panel = (64, panel_top, 508, panel_top + panel_height)
    right_panel = (572, panel_top, 1016, panel_top + panel_height)
    draw.rounded_rectangle(
        left_panel, radius=34, fill=theme.left_fill, outline=theme.left_border, width=8
    )
    draw.rounded_rectangle(
        right_panel, radius=34, fill=theme.right_fill, outline=theme.right_border, width=8
    )

    left_name, left_font = fit_name_font(name=creator_name, draw=draw, bold=True, max_width=390)
    right_name, right_font = fit_name_font(name=opponent_name, draw=draw, bold=True, max_width=390)
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
        fill=theme.left_name_color,
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
        fill=theme.right_name_color,
    )


def draw_scoreboard(
    *,
    draw: ImageDraw.ImageDraw,
    creator_score: int,
    opponent_score: int,
    theme: DuelPanelTheme,
) -> None:
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
    draw.text((score_x, score_y), left_score, font=score_font, fill=theme.left_score_color)
    draw.text((score_x + left_width, score_y), colon, font=score_font, fill=(255, 255, 255, 255))
    draw.text(
        (score_x + left_width + colon_width, score_y),
        right_score,
        font=score_font,
        fill=theme.right_score_color,
    )


__all__ = ["DuelPanelTheme", "build_panel_theme", "draw_name_panels", "draw_scoreboard"]
