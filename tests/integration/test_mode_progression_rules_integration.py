from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.db.models.mode_progress import ModeProgress
from app.db.models.quiz_questions import QuizQuestion as QuizQuestionModel
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.energy.service import EnergyService
from app.game.sessions.service import GameSessionService
from app.game.sessions.service.progression import select_level_weighted

UTC = timezone.utc


def _build_question(
    *,
    question_id: str,
    mode_code: str,
    level: str,
    now_utc: datetime,
) -> QuizQuestionModel:
    return QuizQuestionModel(
        question_id=question_id,
        mode_code=mode_code,
        source_file="progression_rules_seed.csv",
        level=level,
        category="Progression",
        question_text=f"{mode_code} {level} {question_id}?",
        option_1="ok",
        option_2="no",
        option_3="x",
        option_4="y",
        correct_option_id=0,
        correct_answer="ok",
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
            first_name="Progress",
            referred_by_user_id=None,
        )
        return user.id


async def _seed_questions(session, *, now_utc: datetime) -> None:  # noqa: ANN001
    levels = ("A1", "A2", "B1", "B2")
    for mode_code in ("ARTIKEL_SPRINT", "QUICK_MIX_A1A2"):
        for level in levels:
            session.add(
                _build_question(
                    question_id=f"{mode_code.lower()}_{level.lower()}_{uuid4().hex[:8]}",
                    mode_code=mode_code,
                    level=level,
                    now_utc=now_utc,
                )
            )


async def _grant_energy(
    session,  # noqa: ANN001
    *,
    user_id: int,
    amount: int,
    now_utc: datetime,
    key_suffix: str,
) -> None:
    await EnergyService.credit_paid_energy(
        session,
        user_id=user_id,
        amount=amount,
        idempotency_key=f"energy:progression:{key_suffix}",
        now_utc=now_utc,
        source="REFERRAL",
        write_ledger_entry=False,
    )


async def _play_round(
    session,  # noqa: ANN001
    *,
    user_id: int,
    mode_code: str,
    now_utc: datetime,
    index: int,
    selection_seed_override: str | None = None,
) -> str:
    start = await GameSessionService.start_session(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source="MENU",
        idempotency_key=f"{mode_code}:start:{index}:{uuid4().hex[:6]}",
        now_utc=now_utc + timedelta(seconds=index),
        selection_seed_override=selection_seed_override,
    )
    question = await session.get(QuizQuestionModel, start.session.question_id)
    assert question is not None

    await GameSessionService.submit_answer(
        session,
        user_id=user_id,
        session_id=start.session.session_id,
        selected_option=0,
        idempotency_key=f"{mode_code}:answer:{index}:{uuid4().hex[:6]}",
        now_utc=now_utc + timedelta(seconds=index),
    )
    return question.level


async def _start_level_only(
    session,  # noqa: ANN001
    *,
    user_id: int,
    mode_code: str,
    now_utc: datetime,
    index: int,
    selection_seed_override: str,
) -> str:
    start = await GameSessionService.start_session(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source="MENU",
        idempotency_key=f"{mode_code}:only-start:{index}:{uuid4().hex[:6]}",
        now_utc=now_utc + timedelta(minutes=index),
        selection_seed_override=selection_seed_override,
    )
    question = await session.get(QuizQuestionModel, start.session.question_id)
    assert question is not None
    return question.level


def _first_seed_for_target_level(*, current_level: str, mix_step: int, target_level: str) -> str:
    for i in range(1, 10_000):
        seed = f"seed:{mix_step}:{i}"
        if select_level_weighted(current_level, mix_step, selection_seed=seed) == target_level:
            return seed
    raise AssertionError(f"No deterministic seed found for target level {target_level}")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode_code", ["ARTIKEL_SPRINT", "QUICK_MIX_A1A2"])
async def test_new_user_first_20_questions_are_only_a1(mode_code: str) -> None:
    now_utc = datetime(2026, 2, 25, 10, 0, tzinfo=UTC)
    user_id = await _create_user(f"new_user_20_{mode_code}")

    async with SessionLocal.begin() as session:
        await _seed_questions(session, now_utc=now_utc)
        await _grant_energy(
            session,
            user_id=user_id,
            amount=20,
            now_utc=now_utc,
            key_suffix=f"20:{mode_code}",
        )

        seen_levels: list[str] = []
        for i in range(20):
            seen_levels.append(
                await _play_round(
                    session,
                    user_id=user_id,
                    mode_code=mode_code,
                    now_utc=now_utc,
                    index=i,
                )
            )

        assert set(seen_levels) == {"A1"}


@pytest.mark.asyncio
async def test_after_30_attempts_with_75_percent_accuracy_a2_appears_at_mix_start() -> None:
    now_utc = datetime(2026, 2, 25, 11, 0, tzinfo=UTC)
    user_id = await _create_user("gate_30_attempts")

    async with SessionLocal.begin() as session:
        await _seed_questions(session, now_utc=now_utc)
        await _grant_energy(
            session,
            user_id=user_id,
            amount=100,
            now_utc=now_utc,
            key_suffix="gate30",
        )

        for i in range(30):
            level = await _play_round(
                session,
                user_id=user_id,
                mode_code="ARTIKEL_SPRINT",
                now_utc=now_utc,
                index=i,
            )
            assert level == "A1"

        progress_row = await session.get(
            ModeProgress,
            {
                "user_id": user_id,
                "mode_code": "ARTIKEL_SPRINT",
            },
        )
        assert progress_row is not None
        assert progress_row.preferred_level == "A1"
        assert progress_row.mix_step == 1
        assert progress_row.correct_in_mix == 0

        a2_seed = _first_seed_for_target_level(
            current_level="A1",
            mix_step=1,
            target_level="A2",
        )
        seen_level = await _start_level_only(
            session,
            user_id=user_id,
            mode_code="ARTIKEL_SPRINT",
            now_utc=now_utc + timedelta(hours=1),
            index=1,
            selection_seed_override=a2_seed,
        )
        assert seen_level == "A2"


@pytest.mark.asyncio
async def test_user_on_a1_never_sees_b1_or_b2() -> None:
    now_utc = datetime(2026, 2, 25, 12, 0, tzinfo=UTC)
    user_id = await _create_user("a1_never_b1_b2")

    async with SessionLocal.begin() as session:
        await _seed_questions(session, now_utc=now_utc)
        await _grant_energy(
            session,
            user_id=user_id,
            amount=100,
            now_utc=now_utc,
            key_suffix="a1-never-b",
        )

        session.add(
            ModeProgress(
                user_id=user_id,
                mode_code="ARTIKEL_SPRINT",
                preferred_level="A1",
                mix_step=3,
                correct_in_mix=0,
                created_at=now_utc,
                updated_at=now_utc,
            )
        )
        await session.flush()

        seen_levels: set[str] = set()
        for i in range(30):
            seen_levels.add(
                await _start_level_only(
                    session,
                    user_id=user_id,
                    mode_code="ARTIKEL_SPRINT",
                    now_utc=now_utc,
                    index=i,
                    selection_seed_override=f"a1-cap-{i}",
                )
            )

        assert "B1" not in seen_levels
        assert "B2" not in seen_levels
        assert seen_levels.issubset({"A1", "A2"})


@pytest.mark.asyncio
async def test_user_on_a2_never_sees_b2_before_upgrade() -> None:
    now_utc = datetime(2026, 2, 25, 13, 0, tzinfo=UTC)
    user_id = await _create_user("a2_never_b2")

    async with SessionLocal.begin() as session:
        await _seed_questions(session, now_utc=now_utc)
        await _grant_energy(
            session,
            user_id=user_id,
            amount=100,
            now_utc=now_utc,
            key_suffix="a2-never-b2",
        )

        session.add(
            ModeProgress(
                user_id=user_id,
                mode_code="QUICK_MIX_A1A2",
                preferred_level="A2",
                mix_step=3,
                correct_in_mix=0,
                created_at=now_utc,
                updated_at=now_utc,
            )
        )
        await session.flush()

        seen_levels: set[str] = set()
        for i in range(30):
            seen_levels.add(
                await _start_level_only(
                    session,
                    user_id=user_id,
                    mode_code="QUICK_MIX_A1A2",
                    now_utc=now_utc,
                    index=i,
                    selection_seed_override=f"a2-cap-{i}",
                )
            )

        assert "B2" not in seen_levels
        assert seen_levels.issubset({"A2", "B1"})
