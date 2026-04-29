from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.db.models.referrals import Referral
from app.db.repo.referrals_repo import ReferralsRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


def _referral(**overrides: object) -> Referral:
    payload: dict[str, object] = {
        "id": 11,
        "referrer_user_id": 7,
        "referred_user_id": 8,
        "referral_code": "REF7",
        "status": "STARTED",
        "qualified_at": None,
        "rewarded_at": None,
        "notified_at": None,
        "fraud_score": Decimal("0"),
        "created_at": datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
    }
    payload.update(overrides)
    return Referral(**payload)


async def test_create_adds_and_flushes_referral() -> None:
    referral = _referral()
    session = RecordingSession()

    assert await ReferralsRepo.create(session, referral=referral) is referral
    assert session.added == [referral]
    assert session.flushed is True


async def test_mark_started_as_rejected_fraud_locks_and_mutates_rows() -> None:
    first = _referral(id=11)
    second = _referral(id=12, referred_user_id=9)
    session = RecordingSession(_ScalarsResult([first, second]))

    updated_count = await ReferralsRepo.mark_started_as_rejected_fraud(
        session,
        referrer_user_id=7,
        min_created_at_utc=datetime(2026, 3, 1, tzinfo=UTC),
        score=Decimal("95.5"),
    )

    assert updated_count == 2
    assert first.status == "REJECTED_FRAUD"
    assert second.status == "REJECTED_FRAUD"
    assert first.fraud_score == Decimal("95.5")
    assert second.fraud_score == Decimal("95.5")
    sql = compile_statement(session.statement)
    assert "referrals.referrer_user_id = 7" in sql
    assert "referrals.status = 'STARTED'" in sql
    assert "referrals.created_at >=" in sql
    assert "FOR UPDATE" in sql
