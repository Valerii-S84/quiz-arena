from __future__ import annotations

from types import SimpleNamespace


def _fake_record(
    question_id: str,
    *,
    mode_code: str = "QUICK_MIX_A1A2",
    level: str = "A1",
    category: str = "General",
) -> SimpleNamespace:
    return SimpleNamespace(
        question_id=question_id,
        mode_code=mode_code,
        source_file="bank.csv",
        level=level,
        category=category,
        question_text=f"Frage {question_id}?",
        option_1="A",
        option_2="B",
        option_3="C",
        option_4="D",
        correct_option_id=1,
        correct_answer="B",
        explanation="Erklärung.",
        key=question_id,
        status="ACTIVE",
    )
