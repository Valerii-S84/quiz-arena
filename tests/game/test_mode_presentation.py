from __future__ import annotations

from pathlib import Path

from app.game.modes.catalog import FREE_MODE_CODES
from app.game.modes.presentation import display_mode_label
from app.game.questions.catalog import (
    DAILY_CHALLENGE_SOURCE_MODE,
    QUICK_MIX_MODE_CODE,
    QUIZBANK_FILE_TO_MODE_CODE,
)
from app.game.sessions.service.constants import PERSISTENT_ADAPTIVE_MODE_BOUNDS

APP_ROOT = Path(__file__).resolve().parents[2] / "app"


def test_display_mode_label_uses_unified_user_facing_names() -> None:
    assert display_mode_label("ARTIKEL_SPRINT") == "Artikel-Training"
    assert display_mode_label("QUICK_MIX_A1A2") == "Schnell-Runde"
    assert display_mode_label("CASES_PRACTICE") == "Fälle-Training"
    assert display_mode_label("TRENNBARE_VERBEN") == "Trennbare Verben"
    assert display_mode_label("WORD_ORDER") == "Wortstellung"


def test_user_facing_python_files_do_not_contain_legacy_mode_labels() -> None:
    legacy_labels = ("ARTIKEL SPRINT", "Artikel Sprint", "QUICK MIX", "Quick Mix")

    for path in APP_ROOT.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert not any(label in content for label in legacy_labels), path.as_posix()


def test_internal_mode_codes_remain_stable() -> None:
    assert "ARTIKEL_SPRINT" in FREE_MODE_CODES
    assert "CASES_PRACTICE" in FREE_MODE_CODES
    assert "TRENNBARE_VERBEN" in FREE_MODE_CODES
    assert "WORD_ORDER" in FREE_MODE_CODES
    assert "ARTIKEL_SPRINT" in PERSISTENT_ADAPTIVE_MODE_BOUNDS
    assert QUICK_MIX_MODE_CODE == "QUICK_MIX_A1A2"
    assert DAILY_CHALLENGE_SOURCE_MODE == "QUICK_MIX_A1A2"
    assert "QUICK_MIX_A1A2" in FREE_MODE_CODES
    assert "QUICK_MIX_A1A2" in PERSISTENT_ADAPTIVE_MODE_BOUNDS
    assert QUIZBANK_FILE_TO_MODE_CODE["Artikel_Sprint_Bank_A1_B2_1000.csv"] == "ARTIKEL_SPRINT"
