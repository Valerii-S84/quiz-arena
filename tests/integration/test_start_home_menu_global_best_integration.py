from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.bot.handlers import start
from app.db.models.energy_state import EnergyState
from app.db.models.streak_state import StreakState
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from tests.bot.helpers import DummyMessage
from tests.integration.stable_ids import stable_telegram_user_id


class _StartMessage(DummyMessage):
    def __init__(self, *, text: str, from_user: SimpleNamespace, message_id: int = 100) -> None:
        super().__init__()
        self.text = text
        self.from_user = from_user
        self.message_id = message_id


def _berlin_date(now_utc: datetime) -> date:
    return now_utc.astimezone(ZoneInfo("Europe/Berlin")).date()


async def _create_user_with_home_state(
    *,
    seed: str,
    now_utc: datetime,
    current_streak: int,
    best_streak: int,
) -> int:
    telegram_user_id = stable_telegram_user_id(prefix=51_000_000_000, seed=seed)

    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=telegram_user_id,
            referral_code=f"S{uuid4().hex[:10]}",
            username=seed,
            first_name=seed.title(),
            referred_by_user_id=None,
        )
        session.add(
            EnergyState(
                user_id=user.id,
                free_energy=20,
                paid_energy=0,
                free_cap=20,
                regen_interval_sec=1800,
                last_regen_at=now_utc,
                last_daily_topup_local_date=_berlin_date(now_utc),
                version=0,
                updated_at=now_utc,
            )
        )
        session.add(
            StreakState(
                user_id=user.id,
                current_streak=current_streak,
                best_streak=best_streak,
                last_activity_local_date=_berlin_date(now_utc),
                today_status="PLAYED",
                streak_saver_tokens=0,
                streak_saver_last_purchase_at=None,
                premium_freezes_used_week=0,
                premium_freeze_week_start_local_date=None,
                version=0,
                updated_at=now_utc,
            )
        )
        await session.flush()

    return telegram_user_id


@pytest.mark.asyncio
async def test_home_menu_shows_current_user_streak_and_global_best_streak(monkeypatch) -> None:
    now_utc = datetime.now(timezone.utc)
    current_user_telegram_id = await _create_user_with_home_state(
        seed="home-current-user",
        now_utc=now_utc,
        current_streak=14,
        best_streak=14,
    )
    await _create_user_with_home_state(
        seed="home-global-record-holder",
        now_utc=now_utc,
        current_streak=27,
        best_streak=27,
    )

    async def _no_offer(*args, **kwargs):
        del args, kwargs
        return None

    monkeypatch.setattr(start.start_flow.OfferService, "evaluate_and_log_offer", _no_offer)
    monkeypatch.setattr(
        start.start_flow,
        "get_settings",
        lambda: SimpleNamespace(
            resolved_welcome_image_file_id="",
            welcome_image_file_id="",
            telegram_home_header_file_id="",
        ),
    )

    message = _StartMessage(
        text="/start",
        from_user=SimpleNamespace(
            id=current_user_telegram_id,
            username="home-current-user",
            first_name="Current",
            language_code="de",
        ),
    )

    await start.handle_start(message)

    home_text = message.answers[0].text or ""
    assert "Serie: 14 | Beste: 27" in home_text
    assert "Beste: 14" not in home_text
