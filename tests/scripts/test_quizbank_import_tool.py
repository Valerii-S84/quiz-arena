from __future__ import annotations

import pytest

from scripts.quizbank_import_tool import _validate_replace_all_safety

PROD_DB_URL = "postgresql+asyncpg://quiz:secret@db:5432/quiz_arena"


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
