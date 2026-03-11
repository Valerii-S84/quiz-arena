from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.db.models.mode_progress import ModeProgress
from app.db.models.quiz_questions import QuizQuestion as QuizQuestionModel
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.energy.service import EnergyService
from app.game.questions.runtime_bank import clear_question_pool_cache
from app.game.sessions.service import GameSessionService
from tests.integration.stable_ids import stable_telegram_user_id

UTC = timezone.utc
MODE_CODES = ("ARTIKEL_SPRINT", "QUICK_MIX_A1A2")


@pytest.fixture(autouse=True)
def clear_runtime_pool_cache() -> None:
    clear_question_pool_cache()


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
        source_file="progression_parameters_seed.csv",
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
        quick_mix_eligible=mode_code == "QUICK_MIX_A1A2",
        created_at=now_utc,
        updated_at=now_utc,
    )


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=stable_telegram_user_id(prefix=60_000_000_000, seed=seed),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="Progression",
            referred_by_user_id=None,
        )
        return user.id


async def _seed_questions(session, *, now_utc: datetime) -> None:  # noqa: ANN001
    for mode_code in MODE_CODES:
        for level in ("A1", "A2", "B1", "B2"):
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
        idempotency_key=f"energy:progression-params:{key_suffix}",
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
    is_correct: bool,
) -> None:
    start = await GameSessionService.start_session(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source="MENU",
        idempotency_key=f"{mode_code}:params:start:{index}:{uuid4().hex[:6]}",
        now_utc=now_utc + timedelta(seconds=index),
        selection_seed_override=f"{mode_code}:params:seed:{index}",
    )
    await GameSessionService.submit_answer(
        session,
        user_id=user_id,
        session_id=start.session.session_id,
        selected_option=(0 if is_correct else 1),
        idempotency_key=f"{mode_code}:params:answer:{index}:{uuid4().hex[:6]}",
        now_utc=now_utc + timedelta(seconds=index),
    )


async def _progress_row(session, *, user_id: int, mode_code: str) -> ModeProgress:  # noqa: ANN001
    progress_row = await session.get(
        ModeProgress,
        {
            "user_id": user_id,
            "mode_code": mode_code,
        },
    )
    assert progress_row is not None
    return progress_row


@pytest.mark.asyncio
@pytest.mark.parametrize("mode_code", MODE_CODES)
async def test_mix_activation_requires_30_answers(mode_code: str) -> None:
    now_utc = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    user_id = await _create_user(f"warmup_{mode_code}")

    async with SessionLocal.begin() as session:
        await _seed_questions(session, now_utc=now_utc)
        await _grant_energy(
            session,
            user_id=user_id,
            amount=60,
            now_utc=now_utc,
            key_suffix=f"warmup:{mode_code}",
        )

        for index in range(29):
            await _play_round(
                session,
                user_id=user_id,
                mode_code=mode_code,
                now_utc=now_utc,
                index=index,
                is_correct=True,
            )

        progress_row = await _progress_row(session, user_id=user_id, mode_code=mode_code)
        assert progress_row.preferred_level == "A1"
        assert progress_row.mix_step == 0
        assert progress_row.correct_in_mix == 0

        await _play_round(
            session,
            user_id=user_id,
            mode_code=mode_code,
            now_utc=now_utc,
            index=29,
            is_correct=True,
        )

        progress_row = await _progress_row(session, user_id=user_id, mode_code=mode_code)
        assert progress_row.preferred_level == "A1"
        assert progress_row.mix_step == 1
        assert progress_row.correct_in_mix == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode_code", MODE_CODES)
async def test_mix_activation_requires_75_percent_accuracy(mode_code: str) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    user_id = await _create_user(f"accuracy_{mode_code}")

    async with SessionLocal.begin() as session:
        await _seed_questions(session, now_utc=now_utc)
        await _grant_energy(
            session,
            user_id=user_id,
            amount=60,
            now_utc=now_utc,
            key_suffix=f"accuracy:{mode_code}",
        )

        for index in range(22):
            await _play_round(
                session,
                user_id=user_id,
                mode_code=mode_code,
                now_utc=now_utc,
                index=index,
                is_correct=True,
            )
        for index in range(22, 30):
            await _play_round(
                session,
                user_id=user_id,
                mode_code=mode_code,
                now_utc=now_utc,
                index=index,
                is_correct=False,
            )

        progress_row = await _progress_row(session, user_id=user_id, mode_code=mode_code)
        assert progress_row.preferred_level == "A1"
        assert progress_row.mix_step == 0
        assert progress_row.correct_in_mix == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode_code", MODE_CODES)
async def test_10_correct_answers_raise_mix_steps(mode_code: str) -> None:
    now_utc = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    user_id = await _create_user(f"mix_steps_{mode_code}")

    async with SessionLocal.begin() as session:
        await _seed_questions(session, now_utc=now_utc)
        await _grant_energy(
            session,
            user_id=user_id,
            amount=40,
            now_utc=now_utc,
            key_suffix=f"steps:{mode_code}",
        )
        session.add(
            ModeProgress(
                user_id=user_id,
                mode_code=mode_code,
                preferred_level="A1",
                mix_step=1,
                correct_in_mix=0,
                created_at=now_utc,
                updated_at=now_utc,
            )
        )
        await session.flush()

        for index in range(10):
            await _play_round(
                session,
                user_id=user_id,
                mode_code=mode_code,
                now_utc=now_utc,
                index=index,
                is_correct=True,
            )

        progress_row = await _progress_row(session, user_id=user_id, mode_code=mode_code)
        assert progress_row.mix_step == 2
        assert progress_row.correct_in_mix == 0

        for index in range(10, 20):
            await _play_round(
                session,
                user_id=user_id,
                mode_code=mode_code,
                now_utc=now_utc,
                index=index,
                is_correct=True,
            )

        progress_row = await _progress_row(session, user_id=user_id, mode_code=mode_code)
        assert progress_row.mix_step == 3
        assert progress_row.correct_in_mix == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode_code", MODE_CODES)
async def test_10_correct_answers_on_step3_upgrade_level(mode_code: str) -> None:
    now_utc = datetime(2026, 3, 1, 13, 0, tzinfo=UTC)
    user_id = await _create_user(f"level_up_{mode_code}")

    async with SessionLocal.begin() as session:
        await _seed_questions(session, now_utc=now_utc)
        await _grant_energy(
            session,
            user_id=user_id,
            amount=20,
            now_utc=now_utc,
            key_suffix=f"level-up:{mode_code}",
        )
        session.add(
            ModeProgress(
                user_id=user_id,
                mode_code=mode_code,
                preferred_level="A1",
                mix_step=3,
                correct_in_mix=0,
                created_at=now_utc,
                updated_at=now_utc,
            )
        )
        await session.flush()

        for index in range(10):
            await _play_round(
                session,
                user_id=user_id,
                mode_code=mode_code,
                now_utc=now_utc,
                index=index,
                is_correct=True,
            )

        progress_row = await _progress_row(session, user_id=user_id, mode_code=mode_code)
        assert progress_row.preferred_level == "A2"
        assert progress_row.mix_step == 0
        assert progress_row.correct_in_mix == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode_code", MODE_CODES)
async def test_incorrect_answer_does_not_reset_progression(mode_code: str) -> None:
    now_utc = datetime(2026, 3, 1, 14, 0, tzinfo=UTC)
    user_id = await _create_user(f"wrong_answer_{mode_code}")

    async with SessionLocal.begin() as session:
        await _seed_questions(session, now_utc=now_utc)
        await _grant_energy(
            session,
            user_id=user_id,
            amount=10,
            now_utc=now_utc,
            key_suffix=f"wrong:{mode_code}",
        )
        session.add(
            ModeProgress(
                user_id=user_id,
                mode_code=mode_code,
                preferred_level="A1",
                mix_step=2,
                correct_in_mix=4,
                created_at=now_utc,
                updated_at=now_utc,
            )
        )
        await session.flush()

        await _play_round(
            session,
            user_id=user_id,
            mode_code=mode_code,
            now_utc=now_utc,
            index=0,
            is_correct=False,
        )

        progress_row = await _progress_row(session, user_id=user_id, mode_code=mode_code)
        assert progress_row.preferred_level == "A1"
        assert progress_row.mix_step == 2
        assert progress_row.correct_in_mix == 4
