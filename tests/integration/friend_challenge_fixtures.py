from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.db.models.quiz_questions import QuizQuestion as QuizQuestionModel
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=30_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="Friend",
            referred_by_user_id=None,
        )
        return user.id


def _build_question(
    *,
    question_id: str,
    level: str,
    category: str,
    now_utc: datetime,
) -> QuizQuestionModel:
    return QuizQuestionModel(
        question_id=question_id,
        mode_code="QUICK_MIX_A1A2",
        source_file="friend_challenge_seed.csv",
        level=level,
        category=category,
        question_text=f"{level} {category} Frage {question_id}?",
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


async def _seed_friend_challenge_questions(now_utc: datetime) -> None:
    categories = ("Grammar", "Vocabulary", "Dialog", "Cases", "Verbs")
    records: list[QuizQuestionModel] = []

    for idx in range(1, 7):
        records.append(
            _build_question(
                question_id=f"fc_a1_{idx:03d}",
                level="A1",
                category=categories[idx % len(categories)],
                now_utc=now_utc,
            )
        )
    for idx in range(1, 10):
        records.append(
            _build_question(
                question_id=f"fc_a2_{idx:03d}",
                level="A2",
                category=categories[(idx + 1) % len(categories)],
                now_utc=now_utc,
            )
        )
    for idx in range(1, 6):
        records.append(
            _build_question(
                question_id=f"fc_b1_{idx:03d}",
                level="B1",
                category=categories[(idx + 2) % len(categories)],
                now_utc=now_utc,
            )
        )

    async with SessionLocal.begin() as session:
        session.add_all(records)
        await session.flush()
