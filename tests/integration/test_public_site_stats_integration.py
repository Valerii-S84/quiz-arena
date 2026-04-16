from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.api.routes import public_site as public_site_routes
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from tests.integration.stable_ids import stable_telegram_user_id
from tests.type_helpers import as_any_dict

UTC = timezone.utc


@pytest.mark.asyncio
async def test_collect_public_metrics_counts_only_completed_quizzes() -> None:
    started_at = datetime(2026, 4, 6, 12, 0, tzinfo=UTC)
    before_metrics = as_any_dict(await public_site_routes._collect_public_metrics())

    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=stable_telegram_user_id(
                prefix=81_000_000_000, seed="public-site-stats"
            ),
            referral_code="PUBSTATS01",
            username="public-site-stats",
            first_name="Public",
            referred_by_user_id=None,
        )
        session.add_all(
            [
                QuizSession(
                    id=uuid4(),
                    user_id=int(user.id),
                    mode_code="QUICK_MIX_A1A2",
                    source="MENU",
                    status="COMPLETED",
                    energy_cost_total=1,
                    question_id="q-public-1",
                    friend_challenge_id=None,
                    friend_challenge_round=None,
                    started_at=started_at,
                    completed_at=started_at + timedelta(minutes=1),
                    local_date_berlin=date(2026, 4, 6),
                    idempotency_key="public-site-stats:completed",
                ),
                QuizSession(
                    id=uuid4(),
                    user_id=int(user.id),
                    mode_code="QUICK_MIX_A1A2",
                    source="MENU",
                    status="STARTED",
                    energy_cost_total=1,
                    question_id="q-public-2",
                    friend_challenge_id=None,
                    friend_challenge_round=None,
                    started_at=started_at + timedelta(minutes=2),
                    completed_at=None,
                    local_date_berlin=date(2026, 4, 6),
                    idempotency_key="public-site-stats:started",
                ),
            ]
        )

    metrics = as_any_dict(await public_site_routes._collect_public_metrics())

    assert metrics["quizzes_total"] == before_metrics["quizzes_total"] + 1
