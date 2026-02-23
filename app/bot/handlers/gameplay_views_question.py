from __future__ import annotations

import html
from typing import TYPE_CHECKING

from app.bot.texts.de import TEXTS_DE
from app.game.modes.presentation import display_mode_label
from app.game.modes.rules import is_zero_cost_source

if TYPE_CHECKING:
    from app.game.sessions.types import StartSessionResult


def _build_question_text(
    *,
    source: str,
    snapshot_free_energy: int,
    snapshot_paid_energy: int,
    start_result: StartSessionResult,
) -> str:
    theme_label = start_result.session.category or "Allgemein"
    question_number = start_result.session.question_number or 1
    total_questions = start_result.session.total_questions or 1
    mode_line = TEXTS_DE["msg.game.mode"].format(
        mode_code=display_mode_label(start_result.session.mode_code)
    )
    energy_line = TEXTS_DE["msg.game.energy.left"].format(
        free_energy=(
            snapshot_free_energy if is_zero_cost_source(source) else start_result.energy_free
        ),
        paid_energy=(
            snapshot_paid_energy if is_zero_cost_source(source) else start_result.energy_paid
        ),
    )
    theme_line = TEXTS_DE["msg.game.theme"].format(theme=theme_label)
    counter_line = TEXTS_DE["msg.game.question.counter"].format(
        current=question_number,
        total=total_questions,
    )
    return "\n".join(
        [
            f"<b>{html.escape(mode_line)}</b>",
            html.escape(energy_line),
            "",
            html.escape(theme_line),
            "",
            html.escape(counter_line),
            f"<b>{html.escape(start_result.session.text)}</b>",
            "",
            html.escape(TEXTS_DE["msg.game.choose_option"]),
        ]
    )
