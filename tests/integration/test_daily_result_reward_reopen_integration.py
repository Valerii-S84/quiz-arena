from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.bot.handlers.gameplay_flows import daily_result_flow
from app.bot.texts.de import TEXTS_DE
from app.db.models.energy_state import EnergyState
from app.db.models.ledger_entries import LedgerEntry
from app.db.models.purchases import Purchase
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.energy.service import EnergyService
from app.game.questions.runtime_bank import get_question_by_id
from app.game.sessions.errors import FriendChallengePaymentRequiredError
from app.game.sessions.service import FRIEND_CHALLENGE_TICKET_PRODUCT_CODE, GameSessionService
from app.game.sessions.types import AnswerSessionResult, StartSessionResult
from app.services import user_onboarding
from app.services.user_onboarding import UserOnboardingService
from tests.bot.helpers import DummyCallback, DummyMessage
from tests.integration.stable_ids import stable_telegram_user_id

UTC = timezone.utc


class _FrozenDateTime(datetime):
    current = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)


async def _create_user(seed: str) -> tuple[int, int]:
    telegram_user_id = stable_telegram_user_id(prefix=62_000_000_000, seed=seed)
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=telegram_user_id,
            referral_code=f"R{uuid4().hex[:10]}",
            username=seed,
            first_name="Daily Reward",
            referred_by_user_id=None,
        )
        return int(user.id), int(telegram_user_id)


async def _start_daily(
    *,
    user_id: int,
    idempotency_key: str,
    now_utc: datetime,
) -> StartSessionResult:
    async with SessionLocal.begin() as session:
        return await GameSessionService.start_session(
            session,
            user_id=user_id,
            mode_code="DAILY_CHALLENGE",
            source="DAILY_CHALLENGE",
            idempotency_key=idempotency_key,
            now_utc=now_utc,
        )


async def _answer_daily(
    *,
    user_id: int,
    session_id: UUID,
    correct: bool,
    idempotency_key: str,
    now_utc: datetime,
) -> AnswerSessionResult:
    async with SessionLocal.begin() as session:
        quiz_session = await QuizSessionsRepo.get_by_id(session, session_id)
        assert quiz_session is not None

        question = await get_question_by_id(
            session,
            quiz_session.mode_code,
            question_id=quiz_session.question_id or "",
            local_date_berlin=quiz_session.local_date_berlin,
        )
        assert question is not None

        selected_option = question.correct_option if correct else (question.correct_option + 1) % 4
        return await GameSessionService.submit_answer(
            session,
            user_id=user_id,
            session_id=session_id,
            selected_option=selected_option,
            idempotency_key=idempotency_key,
            now_utc=now_utc,
        )


async def _complete_daily(
    *,
    user_id: int,
    score: int,
    started_at: datetime,
) -> AnswerSessionResult:
    last_answer: AnswerSessionResult | None = None
    for idx in range(7):
        started = await _start_daily(
            user_id=user_id,
            idempotency_key=f"daily-result-reopen:start:{user_id}:{idx}",
            now_utc=started_at + timedelta(seconds=idx * 2),
        )
        last_answer = await _answer_daily(
            user_id=user_id,
            session_id=started.session.session_id,
            correct=idx < score,
            idempotency_key=f"daily-result-reopen:answer:{user_id}:{idx}",
            now_utc=started_at + timedelta(seconds=idx * 2 + 1),
        )

    assert last_answer is not None
    assert last_answer.daily_completed is True
    assert last_answer.daily_run_id is not None
    assert last_answer.daily_score == score
    return last_answer


async def _set_free_energy(*, user_id: int, free_energy: int, now_utc: datetime) -> None:
    async with SessionLocal.begin() as session:
        state = await EnergyService.initialize_user_state(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )
        state.free_energy = free_energy


async def _open_daily_result_screen(
    *,
    telegram_user_id: int,
    daily_run_id: UUID,
) -> DummyCallback:
    callback = DummyCallback(
        data=f"daily:result:{daily_run_id}",
        from_user=SimpleNamespace(
            id=telegram_user_id,
            username="daily_result_user",
            first_name="Daily Reward",
            language_code="de",
        ),
        message=DummyMessage(),
    )
    await daily_result_flow.handle_daily_result_screen(
        callback,
        daily_run_id=daily_run_id,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        game_session_service=GameSessionService,
    )
    return callback


@pytest.mark.asyncio
async def test_reopening_daily_result_screen_does_not_duplicate_energy_reward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_at = datetime(2026, 4, 24, 9, 0, tzinfo=UTC)
    user_id, telegram_user_id = await _create_user("daily-result-reopen-energy")
    await _set_free_energy(user_id=user_id, free_energy=7, now_utc=started_at)
    completed = await _complete_daily(user_id=user_id, score=6, started_at=started_at)
    daily_run_id = completed.daily_run_id
    assert daily_run_id is not None

    reward_idempotency_key = f"daily:reward:energy:{daily_run_id}"

    async with SessionLocal.begin() as session:
        state = await session.get(EnergyState, user_id)
        assert state is not None
        assert state.free_energy == 10
        reward_entry = await session.scalar(
            select(LedgerEntry).where(LedgerEntry.idempotency_key == reward_idempotency_key)
        )
        assert reward_entry is not None
        assert reward_entry.amount == 3
        reward_entries_count = int(
            await session.scalar(
                select(func.count(LedgerEntry.id)).where(
                    LedgerEntry.idempotency_key == reward_idempotency_key
                )
            )
            or 0
        )
        assert reward_entries_count == 1

    _FrozenDateTime.current = started_at + timedelta(minutes=5)
    monkeypatch.setattr(user_onboarding, "datetime", _FrozenDateTime)

    first_callback = await _open_daily_result_screen(
        telegram_user_id=telegram_user_id,
        daily_run_id=daily_run_id,
    )
    second_callback = await _open_daily_result_screen(
        telegram_user_id=telegram_user_id,
        daily_run_id=daily_run_id,
    )

    assert first_callback.message.answers[0].text == TEXTS_DE["msg.daily.result.reward.energy3"]
    assert second_callback.message.answers[0].text == TEXTS_DE["msg.daily.result.reward.energy3"]

    async with SessionLocal.begin() as session:
        state = await session.get(EnergyState, user_id)
        assert state is not None
        assert state.free_energy == 10
        reward_entries_count = int(
            await session.scalar(
                select(func.count(LedgerEntry.id)).where(
                    LedgerEntry.idempotency_key == reward_idempotency_key
                )
            )
            or 0
        )
        assert reward_entries_count == 1


@pytest.mark.asyncio
async def test_reopening_daily_result_screen_does_not_duplicate_ticket_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_at = datetime(2026, 4, 24, 10, 0, tzinfo=UTC)
    user_id, telegram_user_id = await _create_user("daily-result-reopen-ticket")
    completed = await _complete_daily(user_id=user_id, score=7, started_at=started_at)
    daily_run_id = completed.daily_run_id
    assert daily_run_id is not None

    reward_idempotency_key = f"daily:reward:ticket:{daily_run_id}"

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_idempotency_key(session, reward_idempotency_key)
        assert purchase is not None
        assert purchase.product_code == FRIEND_CHALLENGE_TICKET_PRODUCT_CODE
        assert purchase.status == "CREDITED"

        credited_tickets = await PurchasesRepo.count_credited_product(
            session,
            user_id=user_id,
            product_code=FRIEND_CHALLENGE_TICKET_PRODUCT_CODE,
        )
        assert credited_tickets == 1

        purchase_credit_count = int(
            await session.scalar(
                select(func.count(LedgerEntry.id)).where(
                    LedgerEntry.purchase_id == purchase.id,
                    LedgerEntry.entry_type == "PURCHASE_CREDIT",
                )
            )
            or 0
        )
        assert purchase_credit_count == 0

    _FrozenDateTime.current = started_at + timedelta(minutes=5)
    monkeypatch.setattr(user_onboarding, "datetime", _FrozenDateTime)

    first_callback = await _open_daily_result_screen(
        telegram_user_id=telegram_user_id,
        daily_run_id=daily_run_id,
    )
    second_callback = await _open_daily_result_screen(
        telegram_user_id=telegram_user_id,
        daily_run_id=daily_run_id,
    )

    assert first_callback.message.answers[0].text == TEXTS_DE["msg.daily.result.reward.ticket"]
    assert second_callback.message.answers[0].text == TEXTS_DE["msg.daily.result.reward.ticket"]

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_idempotency_key(session, reward_idempotency_key)
        assert purchase is not None
        assert purchase.status == "CREDITED"

        credited_tickets = await PurchasesRepo.count_credited_product(
            session,
            user_id=user_id,
            product_code=FRIEND_CHALLENGE_TICKET_PRODUCT_CODE,
        )
        assert credited_tickets == 1

        purchase_credit_count = int(
            await session.scalar(
                select(func.count(LedgerEntry.id)).where(
                    LedgerEntry.purchase_id == purchase.id,
                    LedgerEntry.entry_type == "PURCHASE_CREDIT",
                )
            )
            or 0
        )
        assert purchase_credit_count == 0


@pytest.mark.asyncio
async def test_daily_result_ticket_reward_is_consumed_as_single_paid_friend_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_at = datetime(2026, 4, 25, 9, 0, tzinfo=UTC)
    user_id, telegram_user_id = await _create_user("daily-result-ticket-consumption")
    completed = await _complete_daily(user_id=user_id, score=7, started_at=started_at)
    daily_run_id = completed.daily_run_id
    assert daily_run_id is not None
    reward_idempotency_key = f"daily:reward:ticket:{daily_run_id}"

    _FrozenDateTime.current = started_at + timedelta(minutes=5)
    monkeypatch.setattr(user_onboarding, "datetime", _FrozenDateTime)

    callback = await _open_daily_result_screen(
        telegram_user_id=telegram_user_id,
        daily_run_id=daily_run_id,
    )
    assert callback.message.answers[0].text == TEXTS_DE["msg.daily.result.reward.ticket"]

    async with SessionLocal.begin() as session:
        first = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=started_at + timedelta(minutes=6),
        )
        second = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=started_at + timedelta(minutes=7),
        )
        paid = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=started_at + timedelta(minutes=8),
        )

        assert first.access_type == "FREE"
        assert second.access_type == "FREE"
        assert paid.access_type == "PAID_TICKET"

        with pytest.raises(FriendChallengePaymentRequiredError):
            await GameSessionService.create_friend_challenge(
                session,
                creator_user_id=user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=started_at + timedelta(minutes=9),
            )

        reward_purchase_rows = int(
            await session.scalar(
                select(func.count(Purchase.id)).where(
                    Purchase.idempotency_key == reward_idempotency_key
                )
            )
            or 0
        )
        assert reward_purchase_rows == 1
