from __future__ import annotations

from datetime import datetime, timezone

from app.db.models.promo_attempts import PromoAttempt
from app.db.repo import promo_repo_attempts
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


def _attempt() -> PromoAttempt:
    return PromoAttempt(
        user_id=7,
        normalized_code_hash="a" * 64,
        result="INVALID",
        source="COMMAND",
        attempted_at=datetime(2026, 3, 14, tzinfo=UTC),
        metadata_={},
    )


async def test_create_attempt_adds_and_flushes_attempt() -> None:
    attempt = _attempt()
    session = RecordingSession()

    created = await promo_repo_attempts.create_attempt(session, attempt=attempt)

    assert created is attempt
    assert session.added == [attempt]
    assert session.flushed is True


async def test_count_user_attempts_short_circuits_empty_result_filter() -> None:
    session = RecordingSession()

    count = await promo_repo_attempts.count_user_attempts(
        session,
        user_id=7,
        since_utc=datetime(2026, 3, 14, tzinfo=UTC),
        attempt_results=[],
    )

    assert count == 0
    assert session.statements == []


async def test_count_user_attempts_and_last_attempt_apply_result_filters() -> None:
    since_utc = datetime(2026, 3, 14, tzinfo=UTC)
    count_session = RecordingSession(_ScalarResult(3))

    assert (
        await promo_repo_attempts.count_user_attempts(
            count_session,
            user_id=7,
            since_utc=since_utc,
            attempt_results=("INVALID", "EXPIRED"),
        )
        == 3
    )
    assert count_session.statement is not None
    count_sql = compile_statement(count_session.statement)
    assert "promo_attempts.user_id = 7" in count_sql
    assert "promo_attempts.result IN ('INVALID', 'EXPIRED')" in count_sql

    no_last_session = RecordingSession()
    assert (
        await promo_repo_attempts.get_last_user_attempt_at(
            no_last_session,
            user_id=7,
            since_utc=since_utc,
            attempt_results=[],
        )
        is None
    )
    assert no_last_session.statements == []

    last_at = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    last_session = RecordingSession(_ScalarResult(last_at))
    assert (
        await promo_repo_attempts.get_last_user_attempt_at(
            last_session,
            user_id=7,
            since_utc=since_utc,
            attempt_results=("RATE_LIMITED",),
        )
        == last_at
    )
    assert last_session.statement is not None
    last_sql = compile_statement(last_session.statement)
    assert "max(promo_attempts.attempted_at)" in last_sql
    assert "promo_attempts.result IN ('RATE_LIMITED')" in last_sql


async def test_attempt_aggregate_queries_group_and_detect_abusive_hashes() -> None:
    since_utc = datetime(2026, 3, 14, tzinfo=UTC)
    result_session = RecordingSession(_RowsResult([("INVALID", 4), ("ACCEPTED", 1)]))

    assert await promo_repo_attempts.count_attempts_by_result(
        result_session,
        since_utc=since_utc,
    ) == {"INVALID": 4, "ACCEPTED": 1}
    assert result_session.statement is not None
    assert "GROUP BY promo_attempts.result" in compile_statement(result_session.statement)

    abusive_session = RecordingSession(_ScalarsResult(["hash-a", "hash-b"]))
    assert await promo_repo_attempts.get_abusive_code_hashes(
        abusive_session,
        since_utc=since_utc,
        min_failed_attempts=5,
        min_distinct_users=2,
    ) == ["hash-a", "hash-b"]
    assert abusive_session.statement is not None
    abusive_sql = compile_statement(abusive_session.statement)
    assert "promo_attempts.result IN ('INVALID', 'EXPIRED', 'NOT_APPLICABLE')" in abusive_sql
    assert "count(promo_attempts.id) > 5" in abusive_sql
    assert "count(DISTINCT promo_attempts.user_id) >= 2" in abusive_sql

    count_abusive_session = RecordingSession(_ScalarsResult(["hash-c"]))
    assert (
        await promo_repo_attempts.count_abusive_code_hashes(
            count_abusive_session,
            since_utc=since_utc,
            min_failed_attempts=3,
            min_distinct_users=2,
        )
        == 1
    )
