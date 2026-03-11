from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from app.db.models.quiz_questions import QuizQuestion as QuizQuestionModel
from app.db.session import SessionLocal
from app.game.questions.runtime_bank import clear_question_pool_cache, select_question_for_mode

UTC = timezone.utc


@pytest.fixture(autouse=True)
def clear_runtime_pool_cache() -> None:
    clear_question_pool_cache()


def _build_question(
    *,
    question_id: str,
    mode_code: str,
    level: str,
    source_file: str,
    now_utc: datetime,
    quick_mix_eligible: bool | None = None,
) -> QuizQuestionModel:
    if quick_mix_eligible is None:
        return QuizQuestionModel(
            question_id=question_id,
            mode_code=mode_code,
            source_file=source_file,
            level=level,
            category="Isolation",
            question_text=f"{mode_code} {question_id}?",
            option_1="A",
            option_2="B",
            option_3="C",
            option_4="D",
            correct_option_id=0,
            correct_answer="A",
            explanation="Seed",
            key=question_id,
            status="ACTIVE",
            created_at=now_utc,
            updated_at=now_utc,
        )
    return QuizQuestionModel(
        question_id=question_id,
        mode_code=mode_code,
        source_file=source_file,
        level=level,
        category="Isolation",
        question_text=f"{mode_code} {question_id}?",
        option_1="A",
        option_2="B",
        option_3="C",
        option_4="D",
        correct_option_id=0,
        correct_answer="A",
        explanation="Seed",
        key=question_id,
        status="ACTIVE",
        quick_mix_eligible=quick_mix_eligible,
        created_at=now_utc,
        updated_at=now_utc,
    )


@pytest.mark.asyncio
async def test_quick_mix_pool_excludes_noneligible_active_questions() -> None:
    now_utc = datetime(2026, 3, 11, 10, 0, tzinfo=UTC)
    suffix = uuid4().hex[:8]

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                _build_question(
                    question_id=f"qm_allowed_{suffix}",
                    mode_code="QUICK_MIX_A1A2",
                    level="A1",
                    source_file="quick_mix_allowed_seed.csv",
                    quick_mix_eligible=True,
                    now_utc=now_utc,
                ),
                _build_question(
                    question_id=f"qm_default_false_{suffix}",
                    mode_code="QUICK_MIX_A1A2",
                    level="A1",
                    source_file="quick_mix_default_false_seed.csv",
                    now_utc=now_utc,
                ),
                _build_question(
                    question_id=f"artikel_only_{suffix}",
                    mode_code="ARTIKEL_SPRINT",
                    level="A1",
                    source_file="artikel_only_seed.csv",
                    now_utc=now_utc,
                ),
            ]
        )
        await session.flush()

        quick_mix_selected = await select_question_for_mode(
            session,
            "QUICK_MIX_A1A2",
            local_date_berlin=date(2026, 3, 11),
            recent_question_ids=[],
            selection_seed=f"quick-mix:{suffix}",
        )
        artikel_selected = await select_question_for_mode(
            session,
            "ARTIKEL_SPRINT",
            local_date_berlin=date(2026, 3, 11),
            recent_question_ids=[],
            selection_seed=f"artikel:{suffix}",
        )

    assert quick_mix_selected.question_id == f"qm_allowed_{suffix}"
    assert artikel_selected.question_id == f"artikel_only_{suffix}"


@pytest.mark.asyncio
async def test_quick_mix_anti_repeat_still_excludes_recent_eligible_ids() -> None:
    now_utc = datetime(2026, 3, 11, 10, 30, tzinfo=UTC)
    suffix = uuid4().hex[:8]
    recent_question_id = f"qm_recent_{suffix}"
    fresh_question_id = f"qm_fresh_{suffix}"

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                _build_question(
                    question_id=recent_question_id,
                    mode_code="QUICK_MIX_A1A2",
                    level="A1",
                    source_file="quick_mix_recent_seed.csv",
                    quick_mix_eligible=True,
                    now_utc=now_utc,
                ),
                _build_question(
                    question_id=fresh_question_id,
                    mode_code="WORD_ORDER",
                    level="A1",
                    source_file="quick_mix_cross_mode_seed.csv",
                    quick_mix_eligible=True,
                    now_utc=now_utc,
                ),
            ]
        )
        await session.flush()

        selected = await select_question_for_mode(
            session,
            "QUICK_MIX_A1A2",
            local_date_berlin=date(2026, 3, 11),
            recent_question_ids=[recent_question_id],
            selection_seed=f"quick-mix-repeat:{suffix}",
        )

    assert selected.question_id == fresh_question_id
