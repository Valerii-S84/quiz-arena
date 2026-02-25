from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.db.models.quiz_questions import QuizQuestion as QuizQuestionModel
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.questions.runtime_bank import clear_question_pool_cache
from app.game.sessions.service import GameSessionService

UTC = timezone.utc


def _build_quick_mix_question(
    *,
    question_id: str,
    level: str,
    now_utc: datetime,
) -> QuizQuestionModel:
    return QuizQuestionModel(
        question_id=question_id,
        mode_code="QUICK_MIX_A1A2",
        source_file="quick_mix_hotfix_seed.csv",
        level=level,
        category="Quick Mix",
        question_text=f"Quick Mix {level} {question_id}?",
        option_1="opt1",
        option_2="opt2",
        option_3="opt3",
        option_4="opt4",
        correct_option_id=0,
        correct_answer="opt1",
        explanation="Seed",
        key=question_id,
        status="ACTIVE",
        created_at=now_utc,
        updated_at=now_utc,
    )


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=50_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="QuickMix",
            referred_by_user_id=None,
        )
        return user.id


@pytest.mark.asyncio
async def test_quick_mix_first_question_starts_from_a1() -> None:
    now_utc = datetime(2026, 2, 19, 22, 0, tzinfo=UTC)
    clear_question_pool_cache()
    user_id = await _create_user("quick_mix_start_a1")

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                _build_quick_mix_question(
                    question_id="quick_mix_a1_001",
                    level="A1",
                    now_utc=now_utc,
                ),
                _build_quick_mix_question(
                    question_id="quick_mix_b2_001",
                    level="B2",
                    now_utc=now_utc,
                ),
            ]
        )
        await session.flush()

        start = await GameSessionService.start_session(
            session,
            user_id=user_id,
            mode_code="QUICK_MIX_A1A2",
            source="MENU",
            idempotency_key="quick-mix:first:start",
            now_utc=now_utc,
        )

        question = await session.get(QuizQuestionModel, start.session.question_id)
        assert question is not None
        assert question.mode_code == "QUICK_MIX_A1A2"
        assert question.level == "A1"
