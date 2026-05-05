from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.db.models.quiz_questions import QuizQuestion as QuizQuestionModel
from app.db.session import SessionLocal
from app.game.questions.runtime_bank import clear_question_pool_cache, select_question_for_mode
from app.game.sessions.service.daily_question_sets import ensure_daily_question_set
from app.game.sessions.service.friend_challenges_question_plan import select_duel_question_ids

UTC = timezone.utc


@pytest.fixture(autouse=True)
def clear_runtime_pool_cache() -> None:
    clear_question_pool_cache()


def _question(
    question_id: str,
    *,
    mode_code: str = "QUICK_MIX_A1A2",
    level: str = "A1",
    source_file: str,
    category: str,
    now_utc: datetime,
) -> QuizQuestionModel:
    return QuizQuestionModel(
        question_id=question_id,
        mode_code=mode_code,
        source_file=source_file,
        level=level,
        category=category,
        question_text=f"{question_id}?",
        option_1="A",
        option_2="B",
        option_3="C",
        option_4="D",
        correct_option_id=0,
        correct_answer="A",
        explanation="Seed",
        key=question_id,
        status="ACTIVE",
        quick_mix_eligible=True,
        created_at=now_utc,
        updated_at=now_utc,
    )


async def _load_sources(question_ids: tuple[str, ...] | list[str]) -> list[str]:
    async with SessionLocal.begin() as session:
        records = [
            await session.get(QuizQuestionModel, question_id) for question_id in question_ids
        ]
    assert all(record is not None for record in records)
    return [record.source_file for record in records if record is not None]


@pytest.mark.asyncio
async def test_daily_question_set_uses_unique_sources_and_cross_mode_quick_mix_eligible() -> None:
    now_utc = datetime(2026, 5, 8, 10, 0, tzinfo=UTC)
    levels = ("A1", "A1", "A2", "A2", "A2", "B1", "B1")
    records = [
        _question(
            f"daily_source_{index}",
            mode_code="WORD_ORDER" if index == 4 else "QUICK_MIX_A1A2",
            level=level,
            source_file=f"daily_source_{index}.csv",
            category=f"DailyCategory{index}",
            now_utc=now_utc,
        )
        for index, level in enumerate(levels, start=1)
    ]

    async with SessionLocal.begin() as session:
        session.add_all(records)
        selected = await ensure_daily_question_set(session, berlin_date=date(2026, 5, 8))

    assert len(selected) == 7
    assert "daily_source_4" in selected
    assert len(set(await _load_sources(selected))) == 7


@pytest.mark.asyncio
async def test_quick_mix_runtime_prefers_unused_source_with_real_db_records() -> None:
    now_utc = datetime(2026, 5, 8, 11, 0, tzinfo=UTC)
    async with SessionLocal.begin() as session:
        session.add_all(
            [
                _question(
                    "runtime_recent",
                    source_file="runtime_a.csv",
                    category="Shared",
                    now_utc=now_utc,
                ),
                _question(
                    "runtime_same_source",
                    source_file="runtime_a.csv",
                    category="Other",
                    now_utc=now_utc,
                ),
                _question(
                    "runtime_new_source",
                    source_file="runtime_b.csv",
                    category="Shared",
                    now_utc=now_utc,
                ),
            ]
        )
        selected = await select_question_for_mode(
            session,
            "QUICK_MIX_A1A2",
            local_date_berlin=date(2026, 5, 8),
            recent_question_ids=["runtime_recent"],
            selection_seed="seed-1",
        )

    assert selected.question_id == "runtime_new_source"


@pytest.mark.asyncio
async def test_duel_question_plan_keeps_sources_unique_when_pool_allows_it() -> None:
    now_utc = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    source_files = (
        "duel_a.csv",
        "duel_a.csv",
        "duel_b.csv",
        "duel_c.csv",
        "duel_d.csv",
        "duel_e.csv",
        "duel_f.csv",
        "duel_g.csv",
    )
    records = [
        _question(
            f"duel_source_{index}",
            source_file=source_file,
            category=f"DuelCategory{index}",
            now_utc=now_utc,
        )
        for index, source_file in enumerate(source_files, start=1)
    ]

    async with SessionLocal.begin() as session:
        session.add_all(records)
        selected = await select_duel_question_ids(
            session,
            mode_code="QUICK_MIX_A1A2",
            total_rounds=7,
            now_utc=now_utc,
            challenge_seed="integration-source-diversity",
            preferred_levels_by_round=("A1", "A1", "A1", "A1", "A1", "A2", "A2"),
        )

    assert len(selected) == 7
    assert len(set(await _load_sources(selected))) == 7
