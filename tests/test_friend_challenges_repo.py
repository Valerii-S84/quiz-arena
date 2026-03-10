from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from app.db.repo.friend_challenges_repo import FriendChallengesRepo


class _ScalarResult:
    def __init__(self, value: int) -> None:
        self._value = value

    def scalar_one(self) -> int:
        return self._value


class _RecordingSession:
    def __init__(self, scalar_value: int) -> None:
        self.scalar_value = scalar_value
        self.statement: object | None = None

    async def execute(self, statement: object) -> _ScalarResult:
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


class _RecordingRowsSession:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.statement: object | None = None

    async def execute(self, statement: object) -> _RowsResult:
        self.statement = statement
        return _RowsResult(self.rows)


def _compile_sql(statement: object) -> str:
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
