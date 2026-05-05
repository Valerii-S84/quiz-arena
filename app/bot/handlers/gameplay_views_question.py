from __future__ import annotations

import html
from typing import TYPE_CHECKING

from app.bot.handlers.question_theme_label import sanitize_question_theme_label
from app.bot.texts.de import TEXTS_DE
from app.game.modes.presentation import display_mode_label
from app.game.modes.rules import is_zero_cost_source

if TYPE_CHECKING:
    from app.game.sessions.types import StartSessionResult


_DUEL_THEMELESS_SOURCES = frozenset({"ARENA_DUEL", "FRIEND_CHALLENGE"})


def _build_question_text(
    *,
    source: str,
    snapshot_free_energy: int,
    snapshot_paid_energy: int,
    start_result: StartSessionResult,
) -> str:
    theme_label = sanitize_question_theme_label(start_result.session.category)
    question_number = start_result.session.question_number or 1
    total_questions = start_result.session.total_questions or 1
    header_mode_label = start_result.session.header_mode_label_override or display_mode_label(
        start_result.session.mode_code
    )
    mode_line = TEXTS_DE["msg.game.mode"].format(mode_code=header_mode_label)
    energy_line = TEXTS_DE["msg.game.energy.left"].format(
        free_energy=(
            snapshot_free_energy if is_zero_cost_source(source) else start_result.energy_free
        ),
        paid_energy=(
            snapshot_paid_energy if is_zero_cost_source(source) else start_result.energy_paid
        ),
    )
    counter_line = TEXTS_DE["msg.game.question.counter"].format(
        current=question_number,
        total=total_questions,
    )
    lines = [
        f"<b>{html.escape(mode_line)}</b>",
        html.escape(energy_line),
        "",
    ]
    if source not in _DUEL_THEMELESS_SOURCES:
        theme_line = TEXTS_DE["msg.game.theme"].format(theme=theme_label)
        lines.extend([html.escape(theme_line), ""])
    lines.extend(
        [
            html.escape(counter_line),
            f"<b>{html.escape(start_result.session.text)}</b>",
            "",
            html.escape(TEXTS_DE["msg.game.choose_option"]),
        ]
    )
    return "\n".join(lines)
