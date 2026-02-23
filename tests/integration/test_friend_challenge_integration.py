from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.db.models.entitlements import Entitlement
from app.db.models.quiz_questions import QuizQuestion as QuizQuestionModel
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.purchases.service import PurchaseService
from app.game.questions.runtime_bank import get_question_by_id
from app.game.questions.types import QuizQuestion
from app.game.sessions.errors import (
    FriendChallengeExpiredError,
    FriendChallengePaymentRequiredError,
)
from app.game.sessions.service import GameSessionService

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


@pytest.mark.asyncio
async def test_friend_challenge_uses_same_question_for_both_users_and_updates_round_score() -> None:
    now_utc = datetime(2026, 2, 19, 18, 0, tzinfo=UTC)
    creator_user_id = await _create_user("fc_sameq_creator")
    opponent_user_id = await _create_user("fc_sameq_opponent")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=3,
        )
        await GameSessionService.join_friend_challenge_by_token(
            session,
            user_id=opponent_user_id,
            invite_token=challenge.invite_token,
            now_utc=now_utc,
        )
        creator_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:round1:creator:start",
            now_utc=now_utc,
        )
        opponent_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=opponent_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:round1:opponent:start",
            now_utc=now_utc,
        )

    assert creator_round.start_result is not None
    assert opponent_round.start_result is not None
    assert (
        creator_round.start_result.session.question_id
        == opponent_round.start_result.session.question_id
    )

    creator_session_id = creator_round.start_result.session.session_id
    opponent_session_id = opponent_round.start_result.session.session_id

    async with SessionLocal.begin() as session:
        creator_session = await QuizSessionsRepo.get_by_id(session, creator_session_id)
        assert creator_session is not None
        question = await get_question_by_id(
            session,
            creator_session.mode_code,
            question_id=creator_session.question_id or "",
            local_date_berlin=creator_session.local_date_berlin,
        )
        assert question is not None
        correct_option = question.correct_option

        first_answer = await GameSessionService.submit_answer(
            session,
            user_id=creator_user_id,
            session_id=creator_session_id,
            selected_option=correct_option,
            idempotency_key="fc:round1:creator:answer",
            now_utc=now_utc,
        )
        second_answer = await GameSessionService.submit_answer(
            session,
            user_id=opponent_user_id,
            session_id=opponent_session_id,
            selected_option=(correct_option + 1) % 4,
            idempotency_key="fc:round1:opponent:answer",
            now_utc=now_utc,
        )

    assert first_answer.friend_challenge is not None
    assert first_answer.friend_challenge_round_completed is False
    assert first_answer.friend_challenge_waiting_for_opponent is True

    assert second_answer.friend_challenge is not None
    assert second_answer.friend_challenge_round_completed is True
    assert second_answer.friend_challenge.status == "ACTIVE"
    assert second_answer.friend_challenge.current_round == 2
    assert second_answer.friend_challenge.creator_score == 1
    assert second_answer.friend_challenge.opponent_score == 0


@pytest.mark.asyncio
async def test_friend_challenge_completes_and_sets_winner() -> None:
    now_utc = datetime(2026, 2, 19, 18, 30, tzinfo=UTC)
    creator_user_id = await _create_user("fc_done_creator")
    opponent_user_id = await _create_user("fc_done_opponent")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=1,
        )
        await GameSessionService.join_friend_challenge_by_token(
            session,
            user_id=opponent_user_id,
            invite_token=challenge.invite_token,
            now_utc=now_utc,
        )
        creator_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:done:creator:start",
            now_utc=now_utc,
        )
        opponent_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=opponent_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:done:opponent:start",
            now_utc=now_utc,
        )

    assert creator_round.start_result is not None
    assert opponent_round.start_result is not None

    creator_session_id = creator_round.start_result.session.session_id
    opponent_session_id = opponent_round.start_result.session.session_id

    async with SessionLocal.begin() as session:
        creator_session = await QuizSessionsRepo.get_by_id(session, creator_session_id)
        assert creator_session is not None
        question = await get_question_by_id(
            session,
            creator_session.mode_code,
            question_id=creator_session.question_id or "",
            local_date_berlin=creator_session.local_date_berlin,
        )
        assert question is not None
        correct_option = question.correct_option

        await GameSessionService.submit_answer(
            session,
            user_id=creator_user_id,
            session_id=creator_session_id,
            selected_option=(correct_option + 1) % 4,
            idempotency_key="fc:done:creator:answer",
            now_utc=now_utc,
        )
        final_answer = await GameSessionService.submit_answer(
            session,
            user_id=opponent_user_id,
            session_id=opponent_session_id,
            selected_option=correct_option,
            idempotency_key="fc:done:opponent:answer",
            now_utc=now_utc,
        )

    assert final_answer.friend_challenge is not None
    assert final_answer.friend_challenge_round_completed is True
    assert final_answer.friend_challenge.status == "COMPLETED"
    assert final_answer.friend_challenge.winner_user_id == opponent_user_id


@pytest.mark.asyncio
async def test_friend_challenge_rematch_creates_bound_opponent_duel() -> None:
    now_utc = datetime(2026, 2, 19, 18, 35, tzinfo=UTC)
    creator_user_id = await _create_user("fc_rematch_creator")
    opponent_user_id = await _create_user("fc_rematch_opponent")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=1,
        )
        await GameSessionService.join_friend_challenge_by_token(
            session,
            user_id=opponent_user_id,
            invite_token=challenge.invite_token,
            now_utc=now_utc,
        )
        creator_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:rematch:base:creator:start",
            now_utc=now_utc,
        )
        opponent_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=opponent_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:rematch:base:opponent:start",
            now_utc=now_utc,
        )
        assert creator_round.start_result is not None
        assert opponent_round.start_result is not None

        creator_session = await QuizSessionsRepo.get_by_id(
            session, creator_round.start_result.session.session_id
        )
        assert creator_session is not None
        question = await get_question_by_id(
            session,
            creator_session.mode_code,
            question_id=creator_session.question_id or "",
            local_date_berlin=creator_session.local_date_berlin,
        )
        assert question is not None

        await GameSessionService.submit_answer(
            session,
            user_id=creator_user_id,
            session_id=creator_round.start_result.session.session_id,
            selected_option=question.correct_option,
            idempotency_key="fc:rematch:base:creator:answer",
            now_utc=now_utc,
        )
        final_answer = await GameSessionService.submit_answer(
            session,
            user_id=opponent_user_id,
            session_id=opponent_round.start_result.session.session_id,
            selected_option=(question.correct_option + 1) % 4,
            idempotency_key="fc:rematch:base:opponent:answer",
            now_utc=now_utc,
        )
        assert final_answer.friend_challenge is not None
        assert final_answer.friend_challenge.status == "COMPLETED"

        rematch = await GameSessionService.create_friend_challenge_rematch(
            session,
            initiator_user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            now_utc=now_utc + timedelta(minutes=1),
        )
        assert rematch.creator_user_id == creator_user_id
        assert rematch.opponent_user_id == opponent_user_id
        assert rematch.total_rounds == 1

        rematch_creator_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=rematch.challenge_id,
            idempotency_key="fc:rematch:new:creator:start",
            now_utc=now_utc + timedelta(minutes=2),
        )
        rematch_opponent_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=opponent_user_id,
            challenge_id=rematch.challenge_id,
            idempotency_key="fc:rematch:new:opponent:start",
            now_utc=now_utc + timedelta(minutes=2),
        )

    assert rematch_creator_round.start_result is not None
    assert rematch_opponent_round.start_result is not None
    assert (
        rematch_creator_round.start_result.session.question_id
        == rematch_opponent_round.start_result.session.question_id
    )


@pytest.mark.asyncio
async def test_friend_challenge_start_round_fails_when_expired() -> None:
    now_utc = datetime(2026, 2, 19, 18, 40, tzinfo=UTC)
    creator_user_id = await _create_user("fc_expired_creator")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=3,
        )
        row = await FriendChallengesRepo.get_by_id_for_update(session, challenge.challenge_id)
        assert row is not None
        row.expires_at = now_utc - timedelta(minutes=1)

        with pytest.raises(FriendChallengeExpiredError):
            await GameSessionService.start_friend_challenge_round(
                session,
                user_id=creator_user_id,
                challenge_id=challenge.challenge_id,
                idempotency_key="fc:expired:start",
                now_utc=now_utc,
            )


@pytest.mark.asyncio
async def test_friend_challenge_creator_can_continue_without_waiting_for_opponent() -> None:
    now_utc = datetime(2026, 2, 19, 18, 45, tzinfo=UTC)
    creator_user_id = await _create_user("fc_async_creator")
    opponent_user_id = await _create_user("fc_async_opponent")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=3,
        )
        await GameSessionService.join_friend_challenge_by_token(
            session,
            user_id=opponent_user_id,
            invite_token=challenge.invite_token,
            now_utc=now_utc,
        )
        round_one = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:async:creator:start:1",
            now_utc=now_utc,
        )
        assert round_one.start_result is not None

        creator_session = await QuizSessionsRepo.get_by_id(
            session, round_one.start_result.session.session_id
        )
        assert creator_session is not None
        question = await get_question_by_id(
            session,
            creator_session.mode_code,
            question_id=creator_session.question_id or "",
            local_date_berlin=creator_session.local_date_berlin,
        )
        assert question is not None
        await GameSessionService.submit_answer(
            session,
            user_id=creator_user_id,
            session_id=round_one.start_result.session.session_id,
            selected_option=question.correct_option,
            idempotency_key="fc:async:creator:answer:1",
            now_utc=now_utc,
        )

        round_two = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:async:creator:start:2",
            now_utc=now_utc,
        )

    assert round_two.start_result is not None
    assert round_two.snapshot.current_round >= 2


@pytest.mark.asyncio
async def test_friend_challenge_second_player_reuses_round_question_from_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 2, 19, 18, 50, tzinfo=UTC)
    creator_user_id = await _create_user("fc_shared_round_creator")
    opponent_user_id = await _create_user("fc_shared_round_opponent")

    selection_calls = 0

    async def fake_select_friend_challenge_question(*args, **kwargs):  # noqa: ANN002, ANN003
        nonlocal selection_calls
        selection_calls += 1
        question_id = "qm_a1a2_001" if selection_calls == 1 else "qm_a1a2_002"
        return QuizQuestion(
            question_id=question_id,
            text=f"Question {question_id}",
            options=("A", "B", "C", "D"),
            correct_option=0,
            level="A1",
            category="Test",
        )

    monkeypatch.setattr(
        "app.game.sessions.service.select_friend_challenge_question",
        fake_select_friend_challenge_question,
    )

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=1,
        )
        await GameSessionService.join_friend_challenge_by_token(
            session,
            user_id=opponent_user_id,
            invite_token=challenge.invite_token,
            now_utc=now_utc,
        )
        creator_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:shared:creator:start",
            now_utc=now_utc,
        )
        opponent_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=opponent_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:shared:opponent:start",
            now_utc=now_utc,
        )

    assert creator_round.start_result is not None
    assert opponent_round.start_result is not None
    assert (
        creator_round.start_result.session.question_id
        == opponent_round.start_result.session.question_id
    )
    assert selection_calls == 1


@pytest.mark.asyncio
async def test_friend_challenge_default_uses_12_round_plan_with_level_mix_and_free_energy() -> None:
    now_utc = datetime(2026, 2, 19, 19, 0, tzinfo=UTC)
    await _seed_friend_challenge_questions(now_utc)
    creator_user_id = await _create_user("fc_plan_creator")
    opponent_user_id = await _create_user("fc_plan_opponent")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
        )
        await GameSessionService.join_friend_challenge_by_token(
            session,
            user_id=opponent_user_id,
            invite_token=challenge.invite_token,
            now_utc=now_utc,
        )

    levels: list[str] = []
    categories: list[str] = []
    final_answer = None

    for round_no in range(1, 13):
        async with SessionLocal.begin() as session:
            creator_round = await GameSessionService.start_friend_challenge_round(
                session,
                user_id=creator_user_id,
                challenge_id=challenge.challenge_id,
                idempotency_key=f"fc:plan:round:{round_no}:creator:start",
                now_utc=now_utc + timedelta(minutes=round_no),
            )
            opponent_round = await GameSessionService.start_friend_challenge_round(
                session,
                user_id=opponent_user_id,
                challenge_id=challenge.challenge_id,
                idempotency_key=f"fc:plan:round:{round_no}:opponent:start",
                now_utc=now_utc + timedelta(minutes=round_no),
            )

            assert creator_round.start_result is not None
            assert opponent_round.start_result is not None
            assert (
                creator_round.start_result.session.question_id
                == opponent_round.start_result.session.question_id
            )

            creator_session = await QuizSessionsRepo.get_by_id(
                session, creator_round.start_result.session.session_id
            )
            assert creator_session is not None
            assert creator_session.energy_cost_total == 0

            question = await get_question_by_id(
                session,
                creator_session.mode_code,
                question_id=creator_session.question_id or "",
                local_date_berlin=creator_session.local_date_berlin,
            )
            assert question is not None
            levels.append((question.level or "").upper())
            categories.append(question.category or "")

            await GameSessionService.submit_answer(
                session,
                user_id=creator_user_id,
                session_id=creator_round.start_result.session.session_id,
                selected_option=question.correct_option,
                idempotency_key=f"fc:plan:round:{round_no}:creator:answer",
                now_utc=now_utc + timedelta(minutes=round_no),
            )
            final_answer = await GameSessionService.submit_answer(
                session,
                user_id=opponent_user_id,
                session_id=opponent_round.start_result.session.session_id,
                selected_option=(question.correct_option + 1) % 4,
                idempotency_key=f"fc:plan:round:{round_no}:opponent:answer",
                now_utc=now_utc + timedelta(minutes=round_no),
            )

    assert final_answer is not None
    assert final_answer.friend_challenge is not None
    assert final_answer.friend_challenge.status == "COMPLETED"
    assert len(levels) == 12
    assert levels.count("A1") == 3
    assert levels.count("A2") == 6
    assert levels.count("B1") == 3
    assert len({category for category in categories if category}) >= 3


@pytest.mark.asyncio
async def test_friend_challenge_allows_two_free_then_requires_paid_ticket() -> None:
    now_utc = datetime(2026, 2, 19, 19, 30, tzinfo=UTC)
    creator_user_id = await _create_user("fc_limit_creator")

    async with SessionLocal.begin() as session:
        first = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
        )
        second = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=1),
        )
        assert first.access_type == "FREE"
        assert second.access_type == "FREE"

        with pytest.raises(FriendChallengePaymentRequiredError):
            await GameSessionService.create_friend_challenge(
                session,
                creator_user_id=creator_user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=now_utc + timedelta(minutes=2),
            )

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=creator_user_id,
            product_code="FRIEND_CHALLENGE_5",
            idempotency_key="buy:friend_challenge_ticket:test",
            now_utc=now_utc + timedelta(minutes=3),
        )
        await PurchaseService.apply_successful_payment(
            session,
            user_id=creator_user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id=f"tg_fc_ticket_{uuid4().hex}",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc + timedelta(minutes=4),
        )

        paid_challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=5),
        )
        assert paid_challenge.access_type == "PAID_TICKET"


@pytest.mark.asyncio
async def test_friend_challenge_premium_is_unlimited() -> None:
    now_utc = datetime(2026, 2, 19, 20, 0, tzinfo=UTC)
    creator_user_id = await _create_user("fc_premium_creator")

    async with SessionLocal.begin() as session:
        session.add(
            Entitlement(
                user_id=creator_user_id,
                entitlement_type="PREMIUM",
                scope="PREMIUM_MONTH",
                status="ACTIVE",
                starts_at=now_utc - timedelta(minutes=1),
                ends_at=now_utc + timedelta(days=30),
                source_purchase_id=None,
                idempotency_key=f"test:fc:premium:{uuid4().hex}",
                metadata_={},
                created_at=now_utc,
                updated_at=now_utc,
            )
        )
        await session.flush()

        access_types: list[str] = []
        for idx in range(1, 6):
            challenge = await GameSessionService.create_friend_challenge(
                session,
                creator_user_id=creator_user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=now_utc + timedelta(minutes=idx),
            )
            access_types.append(challenge.access_type)

        assert access_types == ["PREMIUM", "PREMIUM", "PREMIUM", "PREMIUM", "PREMIUM"]
