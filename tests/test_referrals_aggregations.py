from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from app.db.repo import referrals_aggregations

UTC = timezone.utc


class _ScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one(self):
        return self._value


class _RowsResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)


class _RecordingSession:
    def __init__(self, result) -> None:
        self.statement = None
        self._result = result

    async def execute(self, statement):
        self.statement = statement
        return self._result


def _compile_sql(statement: object) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


async def test_count_rewards_for_referrer_between_filters_rewarded_rows() -> None:
    session = _RecordingSession(_ScalarResult(3))
    from_utc = datetime(2026, 3, 1, tzinfo=UTC)
    to_utc = datetime(2026, 4, 1, tzinfo=UTC)

    count = await referrals_aggregations.count_rewards_for_referrer_between(
        session,
        referrer_user_id=7,
        from_utc=from_utc,
        to_utc=to_utc,
    )

    assert count == 3
    assert session.statement is not None
    sql = _compile_sql(session.statement)
    assert "referrals.referrer_user_id = 7" in sql
    assert "referrals.status = 'REWARDED'" in sql
    assert "referrals.rewarded_at IS NOT NULL" in sql


async def test_count_by_status_since_groups_by_status() -> None:
    session = _RecordingSession(_RowsResult([("STARTED", 4), ("REJECTED_FRAUD", 1)]))

    result = await referrals_aggregations.count_by_status_since(
        session,
        since_utc=datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert result == {"STARTED": 4, "REJECTED_FRAUD": 1}
    assert session.statement is not None
    sql = _compile_sql(session.statement)
    assert "GROUP BY referrals.status" in sql


async def test_list_referrer_stats_since_orders_by_rejections_then_total() -> None:
    session = _RecordingSession(
        _RowsResult(
            [
                (7, 5, 2, datetime(2026, 3, 5, tzinfo=UTC)),
                (8, 3, 0, datetime(2026, 3, 4, tzinfo=UTC)),
            ]
        )
    )

    rows = await referrals_aggregations.list_referrer_stats_since(
        session,
        since_utc=datetime(2026, 3, 1, tzinfo=UTC),
        limit=10,
    )

    assert rows == [
        {
            "referrer_user_id": 7,
            "started_total": 5,
            "rejected_fraud_total": 2,
            "last_start_at": datetime(2026, 3, 5, tzinfo=UTC),
        },
        {
            "referrer_user_id": 8,
            "started_total": 3,
            "rejected_fraud_total": 0,
            "last_start_at": datetime(2026, 3, 4, tzinfo=UTC),
        },
    ]
    assert session.statement is not None
    sql = _compile_sql(session.statement)
    assert "ORDER BY rejected_count DESC" in sql
    assert "total_count DESC" in sql
    assert "LIMIT 10" in sql


async def test_list_recent_fraud_cases_since_serializes_rows() -> None:
    session = _RecordingSession(
        _RowsResult(
            [
                (
                    11,
                    7,
                    8,
                    95.0,
                    datetime(2026, 3, 6, 10, 0, tzinfo=UTC),
                    "REJECTED_FRAUD",
                )
            ]
        )
    )

    rows = await referrals_aggregations.list_recent_fraud_cases_since(
        session,
        since_utc=datetime(2026, 3, 1, tzinfo=UTC),
        limit=25,
    )

    assert rows == [
        {
            "referral_id": 11,
            "referrer_user_id": 7,
            "referred_user_id": 8,
            "fraud_score": 95.0,
            "created_at": datetime(2026, 3, 6, 10, 0, tzinfo=UTC),
            "status": "REJECTED_FRAUD",
        }
    ]
    assert session.statement is not None
    sql = _compile_sql(session.statement)
    assert "referrals.status = 'REJECTED_FRAUD'" in sql
    assert "ORDER BY referrals.created_at DESC, referrals.id DESC" in sql
    assert "LIMIT 25" in sql
