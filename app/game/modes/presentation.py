from __future__ import annotations

MODE_LABELS: dict[str, str] = {
    "QUICK_MIX_A1A2": "Schnell-Runde",
    "ARTIKEL_SPRINT": "Artikel-Training",
    "DAILY_CHALLENGE": "DAILY CHALLENGE",
    "CASES_PRACTICE": "Fälle-Training",
    "TRENNBARE_VERBEN": "Trennbare Verben",
    "WORD_ORDER": "Wortstellung",
}


def display_mode_label(mode_code: str) -> str:
    label = MODE_LABELS.get(mode_code)
    if label is not None:
        return label
    return mode_code.replace("_", " ")
