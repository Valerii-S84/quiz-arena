from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects import postgresql

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from tests.type_helpers import AsyncSessionStub
from tests.type_helpers import ScalarResult as _ScalarResult


class _RecordingSession(AsyncSessionStub):
    def __init__(self, scalar_value: int) -> None:
        self.scalar_value = scalar_value
        self.statement: object | None = None

    async def execute(self, statement: object) -> _ScalarResult:  # type: ignore[override]
        self.statement = statement
        return _ScalarResult(self.scalar_value)


class _RowsScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _RowsResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _RowsScalarResult:
        return _RowsScalarResult(self._rows)


class _RecordingRowsSession(AsyncSessionStub):
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.statement: object | None = None

    async def execute(self, statement: object) -> _RowsResult:  # type: ignore[override]
        self.statement = statement
        return _RowsResult(self.rows)


def _compile_sql(statement: Any) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


async def test_count_by_creator_access_type_ignores_tournament_duels() -> None:
    session = _RecordingSession(scalar_value=2)

    count = await FriendChallengesRepo.count_by_creator_access_type(
        session,
        creator_user_id=7,
        access_type="FREE",
    )

    assert count == 2
    assert session.statement is not None

    sql = _compile_sql(session.statement)

    assert "friend_challenges.creator_user_id = 7" in sql
    assert "friend_challenges.access_type = 'FREE'" in sql
    assert "friend_challenges.tournament_match_id IS NULL" in sql


async def test_count_live_for_user_ignores_tournament_duels() -> None:
    session = _RecordingSession(scalar_value=4)

    count = await FriendChallengesRepo.count_live_for_user(session, user_id=11)

    assert count == 4
    assert session.statement is not None

    sql = _compile_sql(session.statement)

    assert "friend_challenges.status IN" in sql
    assert "friend_challenges.creator_user_id = 11" in sql
    assert "friend_challenges.tournament_match_id IS NULL" in sql


async def test_count_created_since_ignores_tournament_duels() -> None:
    session = _RecordingSession(scalar_value=3)
    created_after_utc = datetime(2026, 3, 7, tzinfo=timezone.utc)

    count = await FriendChallengesRepo.count_created_since(
        session,
        creator_user_id=12,
        created_after_utc=created_after_utc,
    )

    assert count == 3
    assert session.statement is not None

    sql = _compile_sql(session.statement)

    assert "friend_challenges.creator_user_id = 12" in sql
    assert "friend_challenges.tournament_match_id IS NULL" in sql


async def test_list_recent_for_user_ignores_tournament_duels() -> None:
    session = _RecordingRowsSession(rows=[])

    rows = await FriendChallengesRepo.list_recent_for_user(session, user_id=13, limit=20)

    assert rows == []
    assert session.statement is not None

    sql = _compile_sql(session.statement)

    assert "friend_challenges.creator_user_id = 13" in sql
    assert "friend_challenges.tournament_match_id IS NULL" in sql


async def test_list_active_due_for_last_chance_for_update_filters_window_and_notification() -> None:
    session = _RecordingRowsSession(rows=[])
    now_utc = datetime(2026, 3, 8, 10, 0, tzinfo=timezone.utc)
    expires_before_utc = datetime(2026, 3, 8, 10, 30, tzinfo=timezone.utc)

    rows = await FriendChallengesRepo.list_active_due_for_last_chance_for_update(
        session,
        now_utc=now_utc,
        expires_before_utc=expires_before_utc,
        limit=10,
    )

    assert rows == []
    assert session.statement is not None

    sql = _compile_sql(session.statement)

    assert "friend_challenges.tournament_match_id IS NULL" in sql
    assert "friend_challenges.expires_at > " in sql
    assert "friend_challenges.expires_at <=" in sql
    assert "friend_challenges.expires_last_chance_notified_at IS NULL" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql


async def test_list_active_due_for_expire_for_update_uses_live_statuses_and_skip_locked() -> None:
    session = _RecordingRowsSession(rows=[])
    now_utc = datetime(2026, 3, 8, 10, 0, tzinfo=timezone.utc)

    rows = await FriendChallengesRepo.list_active_due_for_expire_for_update(
        session,
        now_utc=now_utc,
        limit=5,
    )

    assert rows == []
    assert session.statement is not None

    sql = _compile_sql(session.statement)

    assert "friend_challenges.status IN" in sql
    assert "friend_challenges.expires_at <=" in sql
    assert "friend_challenges.tournament_match_id IS NULL" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql


async def test_list_pending_due_for_expire_for_update_scopes_pending_only() -> None:
    session = _RecordingRowsSession(rows=[])
    now_utc = datetime(2026, 3, 8, 10, 0, tzinfo=timezone.utc)

    rows = await FriendChallengesRepo.list_pending_due_for_expire_for_update(
        session,
        now_utc=now_utc,
        limit=2,
    )

    assert rows == []
    assert session.statement is not None

    sql = _compile_sql(session.statement)

    assert "friend_challenges.status = 'PENDING'" in sql
    assert "friend_challenges.expires_at <=" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql


async def test_list_joined_due_for_walkover_for_update_requires_opponent() -> None:
    session = _RecordingRowsSession(rows=[])
    now_utc = datetime(2026, 3, 8, 10, 0, tzinfo=timezone.utc)

    rows = await FriendChallengesRepo.list_joined_due_for_walkover_for_update(
        session,
        now_utc=now_utc,
        limit=3,
    )

    assert rows == []
    assert session.statement is not None

    sql = _compile_sql(session.statement)

    assert "friend_challenges.opponent_user_id IS NOT NULL" in sql
    assert "friend_challenges.status IN" in sql
    assert "friend_challenges.expires_at <=" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
