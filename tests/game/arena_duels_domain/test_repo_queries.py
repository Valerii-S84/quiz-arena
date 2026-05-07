from uuid import uuid4

import pytest

from app.db.repo.arena_duels_repo import ArenaDuelsRepo
from app.game.arena_duels.constants import ARENA_DUEL_STATUS_ACTIVE, ARENA_DUEL_STATUS_DRAFT

from .support import NOW_UTC, RecordingSession, RowcountRecordingSession, ScalarRecordingSession


@pytest.mark.asyncio
async def test_source_friend_arena_dedupe_finds_any_published_baseline() -> None:
    source_friend_challenge_id = uuid4()
    session = RecordingSession()

    result = await ArenaDuelsRepo.get_source_friend_duel_with_baseline_for_update(
        session, source_friend_challenge_id=source_friend_challenge_id
    )

    assert result is None
    assert session.statement is not None
    compiled = session.statement.compile()
    sql = str(compiled)
    assert compiled.params["source_friend_challenge_id_1"] == source_friend_challenge_id
    assert "arena_duels.source_friend_challenge_id = :source_friend_challenge_id_1" in sql
    assert "arena_duels.status = :status_1" not in sql
    assert "arena_duels.expires_at > :expires_at_1" not in sql
    assert "arena_attempts.score IS NOT NULL" in sql
    assert "arena_attempts.time_ms IS NOT NULL" in sql
    assert "arena_attempts.completed_at IS NOT NULL" in sql


@pytest.mark.asyncio
async def test_arena_repo_expiry_updates_active_and_draft_duels() -> None:
    active_session = RowcountRecordingSession(rowcount=2)
    draft_session = RowcountRecordingSession(rowcount=1)

    active_total = await ArenaDuelsRepo.expire_active_duels(active_session, now_utc=NOW_UTC)
    draft_total = await ArenaDuelsRepo.expire_draft_duels(draft_session, now_utc=NOW_UTC)

    assert active_total == 2
    assert draft_total == 1
    assert active_session.statement is not None
    assert draft_session.statement is not None
    active_sql = str(active_session.statement.compile())
    assert "UPDATE arena_duels" in active_sql
    assert "arena_duels.status = :status_1" in active_sql
    assert "arena_duels.expires_at <= :expires_at_1" in active_sql
    assert active_session.statement.compile().params["status_1"] == ARENA_DUEL_STATUS_ACTIVE
    assert draft_session.statement.compile().params["status_1"] == ARENA_DUEL_STATUS_DRAFT


@pytest.mark.asyncio
async def test_paid_ticket_usage_excludes_friend_published_arena_duels() -> None:
    session = ScalarRecordingSession(values=(2, 3))

    result = await ArenaDuelsRepo.count_paid_ticket_usage(session, user_id=11)

    assert result == 5
    assert len(session.statements) == 2
    duel_sql = str(session.statements[0].compile())
    attempt_sql = str(session.statements[1].compile())
    assert "arena_duels.source_friend_challenge_id IS NULL" in duel_sql
    assert "arena_attempts.role = :role_1" in attempt_sql
    assert "source_friend_challenge_id" not in attempt_sql
