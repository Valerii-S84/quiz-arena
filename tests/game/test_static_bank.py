from __future__ import annotations

from datetime import date

from app.game.questions.static_bank import _question_pool_for_mode, select_question_for_mode

_ALL_LEVELS = {"A1", "A2", "B1", "B2"}


def _assert_question_shape(question, *, mode_code: str) -> None:  # noqa: ANN001
    assert question.question_id
    assert question.text
    assert len(question.options) == 4
    assert 0 <= question.correct_option <= 3
    assert question.level in _ALL_LEVELS
    assert getattr(question, "mode_code", mode_code) == mode_code


def test_static_bank_pools_have_minimum_size() -> None:
    assert len(_question_pool_for_mode("ARTIKEL_SPRINT")) >= 30
    assert len(_question_pool_for_mode("QUICK_MIX_A1A2")) >= 30


def test_static_bank_questions_are_unique_by_text_per_mode() -> None:
    for mode_code in ("ARTIKEL_SPRINT", "QUICK_MIX_A1A2"):
        pool = _question_pool_for_mode(mode_code)
        texts = [question.text for question in pool]
        assert len(texts) == len(set(texts))


def test_artikel_sprint_static_bank_covers_all_levels() -> None:
    levels = {question.level for question in _question_pool_for_mode("ARTIKEL_SPRINT")}
    assert levels == _ALL_LEVELS


def test_quick_mix_static_bank_questions_are_eligible_when_flag_exists() -> None:
    for question in _question_pool_for_mode("QUICK_MIX_A1A2"):
        assert getattr(question, "quick_mix_eligible", True) is True


def test_artikel_sprint_static_bank_questions_are_not_quick_mix_eligible() -> None:
    for question in _question_pool_for_mode("ARTIKEL_SPRINT"):
        assert getattr(question, "quick_mix_eligible", False) is False


def test_static_bank_anti_repeat_can_skip_recent_20_ids() -> None:
    for mode_code in ("ARTIKEL_SPRINT", "QUICK_MIX_A1A2"):
        pool = _question_pool_for_mode(mode_code)
        recent_question_ids = [question.question_id for question in pool[:20]]
        selected = select_question_for_mode(
            mode_code,
            local_date_berlin=date(2026, 3, 11),
            recent_question_ids=recent_question_ids,
            selection_seed=f"anti-repeat:{mode_code}",
        )
        assert selected.question_id not in recent_question_ids


def test_static_bank_questions_match_expected_shape() -> None:
    for mode_code in ("ARTIKEL_SPRINT", "QUICK_MIX_A1A2"):
        for question in _question_pool_for_mode(mode_code):
            _assert_question_shape(question, mode_code=mode_code)
