from __future__ import annotations

MODE_LABELS: dict[str, str] = {
    "QUICK_MIX_A1A2": "QUICK MIX",
    "ARTIKEL_SPRINT": "ARTIKEL SPRINT",
    "DAILY_CHALLENGE": "DAILY CHALLENGE",
    "CASES_PRACTICE": "CASES PRACTICE",
    "TRENNBARE_VERBEN": "TRENNBARE VERBEN",
    "WORD_ORDER": "WORD ORDER",
}


def display_mode_label(mode_code: str) -> str:
    label = MODE_LABELS.get(mode_code)
    if label is not None:
        return label
    return mode_code.replace("_", " ")
