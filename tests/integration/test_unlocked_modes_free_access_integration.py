from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.energy.service import EnergyService
from app.game.sessions.service import GameSessionService
from tests.integration.stable_ids import stable_telegram_user_id

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=stable_telegram_user_id(prefix=61_000_000_000, seed=seed),
            referral_code=f"U{uuid4().hex[:10]}",
            username=None,
            first_name="Unlocked",
            referred_by_user_id=None,
        )
        await EnergyService.initialize_user_state(
            session,
            user_id=user.id,
            now_utc=datetime.now(UTC),
        )
        return user.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode_code",
    ("CASES_PRACTICE", "TRENNBARE_VERBEN", "WORD_ORDER"),
)
async def test_newly_unlocked_modes_start_without_extra_access_requirements(
    mode_code: str,
) -> None:
    user_id = await _create_user(f"free-mode-{mode_code.lower()}")
    now_utc = datetime(2026, 3, 14, 10, 0, tzinfo=UTC)

    async with SessionLocal.begin() as session:
        start = await GameSessionService.start_session(
            session,
            user_id=user_id,
            mode_code=mode_code,
            source="MENU",
            idempotency_key=f"start:{mode_code}:{uuid4().hex[:8]}",
            now_utc=now_utc,
        )

    assert start.session.mode_code == mode_code
    assert start.session.question_id
