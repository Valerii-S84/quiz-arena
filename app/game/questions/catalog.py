from __future__ import annotations

from typing import Final

DAILY_CHALLENGE_SOURCE_MODE = "QUICK_MIX_A1A2"
QUICK_MIX_MODE_CODE = "QUICK_MIX_A1A2"

QUICK_MIX_ELIGIBLE_SOURCE_FILES: Final[frozenset[str]] = frozenset(
    {
        "Adjektivendungen_Beginner_Bank_A1_A2_210.csv",
        "Akkusativ_Dativ_Bank_A1_B1_210.csv",
        "Antonym_Match_Bank_A1_B1_210.csv",
        "LOGIK_LUECKE_Denken_auf_Deutsch_Bank_500.csv",
        "Lexical_Gap_Fill_Bank_A2_B1_210.csv",
        "Mini_Dialog_Bank_A2_B1_210.csv",
        "Modalverben_Bank_210.csv",
        "Negation_Quiz_Bank_A2_B1_210.csv",
        "Plural_Check_Bank_500.csv",
        "Possessive_Adjectives_Bank_A2_B1_210.csv",
        "Preposition_Selection_Bank_A2_B1_210.csv",
        "Satzbau_Bank_A2_B1_210.csv",
        "Synonym_Match_Bank_A1_B1_210.csv",
        "Topic_Vocabulary_Themes_Bank_A2_B1_210.csv",
        "Verb_Conjugation_Bank_A2_B1_210.csv",
        "W_Fragen_Bank_630.csv",
        "trennbare_verben_210_korrigiert.csv",
    }
)
MODE_POOL_FILTERS: Final[dict[str, dict[str, bool]]] = {
    QUICK_MIX_MODE_CODE: {"quick_mix_eligible": True}
}


def mode_requires_quick_mix_eligible(mode_code: str) -> bool:
    return MODE_POOL_FILTERS.get(mode_code, {}).get("quick_mix_eligible", False)


def is_quick_mix_eligible_source_file(source_file: str) -> bool:
    return source_file in QUICK_MIX_ELIGIBLE_SOURCE_FILES


QUIZBANK_FILE_TO_MODE_CODE: dict[str, str] = {
    "Adjektivendungen_Beginner_Bank_A1_A2_210.csv": QUICK_MIX_MODE_CODE,
    "Akkusativ_Dativ_Bank_A1_B1_210.csv": "CASES_PRACTICE",
    "Antonym_Match_Bank_A1_B1_210.csv": QUICK_MIX_MODE_CODE,
    "Artikel_Sprint_Bank_A1_B2_1000.csv": "ARTIKEL_SPRINT",
    "LOGIK_LUECKE_Denken_auf_Deutsch_Bank_500.csv": QUICK_MIX_MODE_CODE,
    "Lexical_Gap_Fill_Bank_A2_B1_210.csv": QUICK_MIX_MODE_CODE,
    "Mini_Dialog_Bank_A2_B1_210.csv": QUICK_MIX_MODE_CODE,
    "Modalverben_Bank_210.csv": QUICK_MIX_MODE_CODE,
    "Negation_Quiz_Bank_A2_B1_210.csv": QUICK_MIX_MODE_CODE,
    "Plural_Check_Bank_500.csv": QUICK_MIX_MODE_CODE,
    "Possessive_Adjectives_Bank_A2_B1_210.csv": QUICK_MIX_MODE_CODE,
    "Preposition_Selection_Bank_A2_B1_210.csv": QUICK_MIX_MODE_CODE,
    "Satzbau_Bank_A2_B1_210.csv": "WORD_ORDER",
    "Synonym_Match_Bank_A1_B1_210.csv": QUICK_MIX_MODE_CODE,
    "Topic_Vocabulary_Themes_Bank_A2_B1_210.csv": QUICK_MIX_MODE_CODE,
    "Verb_Conjugation_Bank_A2_B1_210.csv": QUICK_MIX_MODE_CODE,
    "W_Fragen_Bank_630.csv": QUICK_MIX_MODE_CODE,
    "trennbare_verben_210_korrigiert.csv": "TRENNBARE_VERBEN",
}
