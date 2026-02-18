from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select

from app.db.models.entitlements import Entitlement
from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
from app.db.models.referrals import Referral
from app.db.models.users import User
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.energy.constants import BERLIN_TIMEZONE
from app.economy.referrals.constants import REFERRAL_STARTS_DAILY_LIMIT, REWARD_CODE_PREMIUM_STARTER
from app.economy.referrals.service import ReferralService
from app.services.user_onboarding import UserOnboardingService

UTC = timezone.utc


def _berlin_date(at_utc: datetime) -> date:
    return at_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()


def _telegram_user(telegram_user_id: int) -> TelegramUser:
    return TelegramUser(
        id=telegram_user_id,
        is_bot=False,
        first_name="Referral",
        username=None,
        language_code="de",
    )


async def _create_user(seed: str) -> User:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=50_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"X{uuid4().hex[:10].upper()}",
            username=None,
            first_name="User",
            referred_by_user_id=None,
        )
        return user


async def _seed_attempts(
    *,
    user_id: int,
    attempts_per_day: int,
    day_offsets: tuple[int, ...],
    now_utc: datetime,
) -> None:
    async with SessionLocal.begin() as session:
        for day_offset in day_offsets:
            base = now_utc - timedelta(days=day_offset)
            local_date = _berlin_date(base)
            for idx in range(attempts_per_day):
                started_at = base + timedelta(minutes=idx)
                session_id = uuid4()
                session.add(
                    QuizSession(
                        id=session_id,
                        user_id=user_id,
                        mode_code="QUICK_MIX_A1A2",
                        source="MENU",
                        status="COMPLETED",
                        energy_cost_total=1,
                        question_id=f"q_{day_offset}_{idx}",
                        started_at=started_at,
                        completed_at=started_at,
                        local_date_berlin=local_date,
                        idempotency_key=f"seed:session:{user_id}:{day_offset}:{idx}",
                    )
                )
                await session.flush()
                session.add(
                    QuizAttempt(
                        session_id=session_id,
                        user_id=user_id,
                        question_id=f"q_{day_offset}_{idx}",
                        is_correct=True,
                        answered_at=started_at,
                        response_ms=1000,
                        idempotency_key=f"seed:attempt:{user_id}:{day_offset}:{idx}",
                    )
                )
        await session.flush()


async def _create_referral_row(
    *,
    referrer_user_id: int,
    referred_user_id: int,
    referral_code: str,
    status: str,
    created_at: datetime,
    qualified_at: datetime | None = None,
) -> None:
    async with SessionLocal.begin() as session:
        session.add(
            Referral(
                referrer_user_id=referrer_user_id,
                referred_user_id=referred_user_id,
                referral_code=referral_code,
                status=status,
                qualified_at=qualified_at,
                rewarded_at=None,
                fraud_score=0,
                created_at=created_at,
            )
        )
        await session.flush()


@pytest.mark.asyncio
async def test_start_payload_referral_creates_started_referral_for_new_user() -> None:
    referrer = await _create_user("referrer-start")
    payload = f"ref_{referrer.referral_code}"

    telegram_user = _telegram_user(60_000_000_001)
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
            start_payload=payload,
        )
        referred_user = await UsersRepo.get_by_id(session, snapshot.user_id)
        assert referred_user is not None
        assert referred_user.referred_by_user_id == referrer.id

        stmt = select(Referral).where(Referral.referred_user_id == referred_user.id)
        referral = await session.scalar(stmt)
        assert referral is not None
        assert referral.referrer_user_id == referrer.id
        assert referral.status == "STARTED"


@pytest.mark.asyncio
async def test_existing_user_start_payload_does_not_rebind_referrer() -> None:
    referrer_a = await _create_user("referrer-a")
    referrer_b = await _create_user("referrer-b")
    telegram_user = _telegram_user(60_000_000_101)

    async with SessionLocal.begin() as session:
        first = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
            start_payload=f"ref_{referrer_a.referral_code}",
        )
        second = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
            start_payload=f"ref_{referrer_b.referral_code}",
        )
        assert first.user_id == second.user_id

        user = await UsersRepo.get_by_id(session, first.user_id)
        assert user is not None
        assert user.referred_by_user_id == referrer_a.id

        stmt = select(func.count(Referral.id)).where(Referral.referred_user_id == first.user_id)
        assert int(await session.scalar(stmt) or 0) == 1


@pytest.mark.asyncio
async def test_referral_qualification_requires_20_attempts_on_two_local_days() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-qual")
    referred = await _create_user("referred-qual")

    await _create_referral_row(
        referrer_user_id=referrer.id,
        referred_user_id=referred.id,
        referral_code=referrer.referral_code,
        status="STARTED",
        created_at=now_utc - timedelta(days=3),
    )
    await _seed_attempts(
        user_id=referred.id,
        attempts_per_day=10,
        day_offsets=(1, 2),
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        result = await ReferralService.run_qualification_checks(session, now_utc=now_utc)
        assert result["qualified"] == 1

        stmt = select(Referral).where(Referral.referred_user_id == referred.id)
        referral = await session.scalar(stmt)
        assert referral is not None
        assert referral.status == "QUALIFIED"
        assert referral.qualified_at is not None


@pytest.mark.asyncio
async def test_referral_rewards_apply_after_48h_delay_and_require_three_qualified() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-reward")
    referred_users = [await _create_user(f"referred-reward-{idx}") for idx in range(3)]

    for idx, referred in enumerate(referred_users):
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=5),
            qualified_at=now_utc - timedelta(hours=47 if idx == 0 else 49),
        )

    async with SessionLocal.begin() as session:
        early = await ReferralService.run_reward_distribution(session, now_utc=now_utc)
        assert early["rewards_granted"] == 0

    async with SessionLocal.begin() as session:
        late = await ReferralService.run_reward_distribution(
            session,
            now_utc=now_utc + timedelta(hours=2),
        )
        assert late["rewards_granted"] == 1

        rewarded_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "REWARDED",
        )
        rewarded_count = int(await session.scalar(rewarded_stmt) or 0)
        assert rewarded_count == 1


@pytest.mark.asyncio
async def test_referral_monthly_limit_defers_third_reward_and_releases_next_month() -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-month-cap")
    referred_users = [await _create_user(f"referred-month-cap-{idx}") for idx in range(9)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=7),
            qualified_at=now_utc - timedelta(days=3),
        )

    async with SessionLocal.begin() as session:
        first_month = await ReferralService.run_reward_distribution(session, now_utc=now_utc)
        assert first_month["rewards_granted"] == 2
        assert first_month["deferred_limit"] >= 1

        deferred_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "DEFERRED_LIMIT",
        )
        assert int(await session.scalar(deferred_stmt) or 0) >= 1

    async with SessionLocal.begin() as session:
        next_month = await ReferralService.run_reward_distribution(
            session,
            now_utc=datetime(2026, 3, 2, 0, 10, tzinfo=UTC),
        )
        assert next_month["rewards_granted"] >= 1


@pytest.mark.asyncio
async def test_started_referral_with_deleted_user_is_canceled() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-cancel")
    referred = await _create_user("referred-cancel")

    async with SessionLocal.begin() as session:
        user = await UsersRepo.get_by_id(session, referred.id)
        assert user is not None
        user.status = "DELETED"

    await _create_referral_row(
        referrer_user_id=referrer.id,
        referred_user_id=referred.id,
        referral_code=referrer.referral_code,
        status="STARTED",
        created_at=now_utc - timedelta(days=1),
    )

    async with SessionLocal.begin() as session:
        result = await ReferralService.run_qualification_checks(session, now_utc=now_utc)
        assert result["canceled"] == 1

        stmt = select(Referral).where(Referral.referred_user_id == referred.id)
        referral = await session.scalar(stmt)
        assert referral is not None
        assert referral.status == "CANCELED"


@pytest.mark.asyncio
async def test_velocity_limit_marks_extra_referral_as_rejected_fraud() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-velocity")

    for idx in range(REFERRAL_STARTS_DAILY_LIMIT + 1):
        referred = await _create_user(f"referred-velocity-{idx}")
        async with SessionLocal.begin() as session:
            referred_model = await UsersRepo.get_by_id(session, referred.id)
            assert referred_model is not None
            await ReferralService.register_start_for_new_user(
                session,
                referred_user=referred_model,
                referral_code=referrer.referral_code,
                now_utc=now_utc,
            )

    async with SessionLocal.begin() as session:
        stmt = (
            select(Referral)
            .where(Referral.referrer_user_id == referrer.id)
            .order_by(Referral.id.desc())
            .limit(1)
        )
        last_referral = await session.scalar(stmt)
        assert last_referral is not None
        assert last_referral.status == "REJECTED_FRAUD"


@pytest.mark.asyncio
async def test_referrer_overview_reports_progress_and_claimable_reward() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-overview")
    referred_users = [await _create_user(f"referred-overview-{idx}") for idx in range(3)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=5),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async with SessionLocal.begin() as session:
        overview = await ReferralService.get_referrer_overview(
            session,
            user_id=referrer.id,
            now_utc=now_utc,
        )
        assert overview is not None
        assert overview.qualified_total == 3
        assert overview.progress_qualified == 3
        assert overview.pending_rewards_total == 1
        assert overview.claimable_rewards == 1
        assert overview.next_reward_at_utc is None


@pytest.mark.asyncio
async def test_reward_distribution_without_reward_code_keeps_reward_for_choice() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-awaiting-choice")
    referred_users = [await _create_user(f"referred-awaiting-choice-{idx}") for idx in range(3)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=4),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async with SessionLocal.begin() as session:
        result = await ReferralService.run_reward_distribution(
            session,
            now_utc=now_utc,
            reward_code=None,
        )
        assert result["rewards_granted"] == 0
        assert result["awaiting_choice"] == 1

        rewarded_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "REWARDED",
        )
        assert int(await session.scalar(rewarded_stmt) or 0) == 0


@pytest.mark.asyncio
async def test_claim_next_reward_choice_grants_selected_reward() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-claim-choice")
    referred_users = [await _create_user(f"referred-claim-choice-{idx}") for idx in range(3)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=4),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async with SessionLocal.begin() as session:
        claim = await ReferralService.claim_next_reward_choice(
            session,
            user_id=referrer.id,
            reward_code=REWARD_CODE_PREMIUM_STARTER,
            now_utc=now_utc,
        )
        assert claim is not None
        assert claim.status == "CLAIMED"
        assert claim.reward_code == REWARD_CODE_PREMIUM_STARTER
        assert claim.overview.rewarded_total == 1

        rewarded_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "REWARDED",
        )
        assert int(await session.scalar(rewarded_stmt) or 0) == 1

        entitlement_stmt = select(func.count(Entitlement.id)).where(
            Entitlement.user_id == referrer.id,
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.status == "ACTIVE",
        )
        assert int(await session.scalar(entitlement_stmt) or 0) == 1


@pytest.mark.asyncio
async def test_claim_next_reward_choice_is_idempotent_on_duplicate_tap() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-claim-idempotent")
    referred_users = [await _create_user(f"referred-claim-idempotent-{idx}") for idx in range(3)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=4),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async with SessionLocal.begin() as session:
        first = await ReferralService.claim_next_reward_choice(
            session,
            user_id=referrer.id,
            reward_code=REWARD_CODE_PREMIUM_STARTER,
            now_utc=now_utc,
        )
        second = await ReferralService.claim_next_reward_choice(
            session,
            user_id=referrer.id,
            reward_code=REWARD_CODE_PREMIUM_STARTER,
            now_utc=now_utc,
        )

    assert first is not None
    assert second is not None
    assert first.status == "CLAIMED"
    assert second.status == "NO_REWARD"

    async with SessionLocal.begin() as session:
        rewarded_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "REWARDED",
        )
        assert int(await session.scalar(rewarded_stmt) or 0) == 1

        entitlement_stmt = select(func.count(Entitlement.id)).where(
            Entitlement.user_id == referrer.id,
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.status == "ACTIVE",
        )
        assert int(await session.scalar(entitlement_stmt) or 0) == 1


@pytest.mark.asyncio
async def test_claim_next_reward_choice_is_safe_under_concurrent_duplicate_callbacks() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-claim-concurrent")
    referred_users = [await _create_user(f"referred-claim-concurrent-{idx}") for idx in range(3)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=4),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async def _claim_once() -> str:
        async with SessionLocal.begin() as session:
            claim = await ReferralService.claim_next_reward_choice(
                session,
                user_id=referrer.id,
                reward_code=REWARD_CODE_PREMIUM_STARTER,
                now_utc=now_utc,
            )
            assert claim is not None
            return claim.status

    statuses = await asyncio.gather(_claim_once(), _claim_once())
    assert statuses.count("CLAIMED") == 1
    assert statuses.count("NO_REWARD") == 1

    async with SessionLocal.begin() as session:
        rewarded_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "REWARDED",
        )
        assert int(await session.scalar(rewarded_stmt) or 0) == 1

        entitlement_stmt = select(func.count(Entitlement.id)).where(
            Entitlement.user_id == referrer.id,
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.status == "ACTIVE",
        )
        assert int(await session.scalar(entitlement_stmt) or 0) == 1


@pytest.mark.asyncio
async def test_worker_awaiting_choice_and_user_claim_race_is_stable() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-worker-choice-race")
    referred_users = [await _create_user(f"referred-worker-choice-race-{idx}") for idx in range(3)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=4),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async def _run_worker() -> dict[str, int]:
        async with SessionLocal.begin() as session:
            return await ReferralService.run_reward_distribution(
                session,
                now_utc=now_utc,
                reward_code=None,
            )

    async def _claim_once() -> str:
        async with SessionLocal.begin() as session:
            claim = await ReferralService.claim_next_reward_choice(
                session,
                user_id=referrer.id,
                reward_code=REWARD_CODE_PREMIUM_STARTER,
                now_utc=now_utc,
            )
            assert claim is not None
            return claim.status

    worker_result, claim_status = await asyncio.gather(_run_worker(), _claim_once())
    assert claim_status == "CLAIMED"
    assert worker_result["awaiting_choice"] in {0, 1}

    async with SessionLocal.begin() as session:
        rewarded_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "REWARDED",
        )
        assert int(await session.scalar(rewarded_stmt) or 0) == 1

        entitlement_stmt = select(func.count(Entitlement.id)).where(
            Entitlement.user_id == referrer.id,
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.status == "ACTIVE",
        )
        assert int(await session.scalar(entitlement_stmt) or 0) == 1
