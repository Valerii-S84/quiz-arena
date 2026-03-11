from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from app.game.questions.catalog import QUICK_MIX_ELIGIBLE_SOURCE_FILES
from scripts.quizbank_import_tool import _build_records, _validate_replace_all_safety

PROD_DB_URL = "postgresql+asyncpg://quiz:secret@db:5432/quiz_arena"
EXPECTED_QUICK_MIX_SOURCE_FILES = {
    "Adjektivendungen_Beginner_Bank_A1_A2_210.csv",
    "Antonym_Match_Bank_A1_B1_210.csv",
    "LOGIK_LUECKE_Denken_auf_Deutsch_Bank_500.csv",
    "Lexical_Gap_Fill_Bank_A2_B1_210.csv",
    "Mini_Dialog_Bank_A2_B1_210.csv",
    "Modalverben_Bank_210.csv",
    "Negation_Quiz_Bank_A2_B1_210.csv",
    "Plural_Check_Bank_500.csv",
    "Possessive_Adjectives_Bank_A2_B1_210.csv",
    "Preposition_Selection_Bank_A2_B1_210.csv",
    "Synonym_Match_Bank_A1_B1_210.csv",
    "Topic_Vocabulary_Themes_Bank_A2_B1_210.csv",
    "Verb_Conjugation_Bank_A2_B1_210.csv",
    "W_Fragen_Bank_630.csv",
}


def _write_quizbank_csv(path: Path, *, question_id: str) -> None:
    path.write_text(
        "\n".join(
            (
                "quiz_id,question,option_1,option_2,option_3,option_4,"
                "correct_option_id,correct_answer,explanation,level,category,key,status",
                f"{question_id},Frage?,A,B,C,D,1,B,Erklaerung,A1,Grammar,{question_id},ready",
            )
        ),
        encoding="utf-8",
    )


def test_validate_replace_all_safety_skips_when_replace_all_is_disabled() -> None:
    _validate_replace_all_safety(
        app_env="production",
        database_url=PROD_DB_URL,
        replace_all=False,
        confirmation_value="",
        expected_db_name="",
    )


def test_validate_replace_all_safety_skips_outside_production() -> None:
    _validate_replace_all_safety(
        app_env="dev",
        database_url=PROD_DB_URL,
        replace_all=True,
        confirmation_value="",
        expected_db_name="",
    )


def test_validate_replace_all_safety_rejects_missing_confirmation() -> None:
    with pytest.raises(RuntimeError, match="explicit confirmation"):
        _validate_replace_all_safety(
            app_env="production",
            database_url=PROD_DB_URL,
            replace_all=True,
            confirmation_value="",
            expected_db_name="quiz_arena",
        )


def test_validate_replace_all_safety_applies_to_prod_alias() -> None:
    with pytest.raises(RuntimeError, match="explicit confirmation"):
        _validate_replace_all_safety(
            app_env="prod",
            database_url=PROD_DB_URL,
            replace_all=True,
            confirmation_value="",
            expected_db_name="quiz_arena",
        )


def test_validate_replace_all_safety_rejects_db_name_mismatch() -> None:
    with pytest.raises(RuntimeError, match="expected DB name mismatch"):
        _validate_replace_all_safety(
            app_env="production",
            database_url=PROD_DB_URL,
            replace_all=True,
            confirmation_value="PROD_REPLACE_ALL_OK",
            expected_db_name="wrong_db",
        )


def test_validate_replace_all_safety_allows_confirmed_production_replace_all() -> None:
    _validate_replace_all_safety(
        app_env="production",
        database_url=PROD_DB_URL,
        replace_all=True,
        confirmation_value="PROD_REPLACE_ALL_OK",
        expected_db_name="quiz_arena",
    )


def test_quick_mix_eligible_source_file_whitelist_is_pinned() -> None:
    assert QUICK_MIX_ELIGIBLE_SOURCE_FILES == EXPECTED_QUICK_MIX_SOURCE_FILES


def test_build_records_marks_only_quick_mix_whitelist_sources_as_eligible(tmp_path: Path) -> None:
    _write_quizbank_csv(
        tmp_path / "Adjektivendungen_Beginner_Bank_A1_A2_210.csv",
        question_id="qm_seed_1",
    )
    _write_quizbank_csv(
        tmp_path / "Artikel_Sprint_Bank_A1_B2_1000.csv",
        question_id="artikel_seed_1",
    )

    records, summary, by_mode = _build_records(
        Namespace(
            input_dir=tmp_path,
            replace_all=False,
            allow_unmapped=False,
            dry_run=True,
        )
    )

    assert summary.total_rows_imported == 2
    assert by_mode["QUICK_MIX_A1A2"] == 1
    assert by_mode["ARTIKEL_SPRINT"] == 1
    eligibility_by_source = {
        str(record["source_file"]): bool(record["quick_mix_eligible"]) for record in records
    }
    assert eligibility_by_source == {
        "Adjektivendungen_Beginner_Bank_A1_A2_210.csv": True,
        "Artikel_Sprint_Bank_A1_B2_1000.csv": False,
    }
