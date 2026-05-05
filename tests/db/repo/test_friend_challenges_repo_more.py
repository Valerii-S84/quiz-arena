from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult
from tests.type_helpers import build_friend_challenge

UTC = timezone.utc


async def test_friend_challenge_core_lookups_create_and_counts() -> None:
    challenge = build_friend_challenge()
    challenge_id = challenge.id

    get_session = RecordingSession(get_result=challenge)
    assert await FriendChallengesRepo.get_by_id(get_session, challenge_id) is challenge
    assert get_session.get_calls == [(FriendChallenge, challenge_id)]

    lock_session = RecordingSession(_ScalarResult(challenge))
    assert await FriendChallengesRepo.get_by_id_for_update(lock_session, challenge_id) is challenge
    assert "FOR UPDATE" in compile_statement(lock_session.statement)

    invite_session = RecordingSession(_ScalarResult(challenge))
    await FriendChallengesRepo.get_by_invite_token(invite_session, "invite-token")
    assert "friend_challenges.invite_token = 'invite-token'" in compile_statement(
        invite_session.statement
    )

    invite_lock_session = RecordingSession(_ScalarResult(challenge))
    await FriendChallengesRepo.get_by_invite_token_for_update(invite_lock_session, "invite-token")
    assert "FOR UPDATE" in compile_statement(invite_lock_session.statement)

    create_session = RecordingSession()
    assert await FriendChallengesRepo.create(create_session, challenge=challenge) is challenge
    assert create_session.added == [challenge]
    assert create_session.flushed is True

    since = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    creator_session = RecordingSession(_ScalarResult(2))
    assert (
        await FriendChallengesRepo.count_by_creator_access_type(
            creator_session,
            creator_user_id=10,
            access_type="FREE",
            since=since,
        )
        == 2
    )
    creator_sql = compile_statement(creator_session.statement)
    assert "friend_challenges.creator_user_id = 10" in creator_sql
    assert "friend_challenges.created_at >=" in creator_sql

    live_session = RecordingSession(_ScalarResult(None))
    assert await FriendChallengesRepo.count_live_for_user(live_session, user_id=10) == 0
    assert "friend_challenges.status IN" in compile_statement(live_session.statement)


async def test_friend_challenge_recent_and_deadline_queries_are_ordered_and_locked() -> None:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    challenge = build_friend_challenge()

    open_session = RecordingSession(_ScalarResult(3))
    assert (
        await FriendChallengesRepo.count_live_open_by_creator(
            open_session,
            creator_user_id=10,
        )
        == 3
    )
    assert "friend_challenges.challenge_type = 'OPEN'" in compile_statement(open_session.statement)

    created_session = RecordingSession(_ScalarResult(4))
    assert (
        await FriendChallengesRepo.count_created_since(
            created_session,
            creator_user_id=10,
            created_after_utc=now_utc,
        )
        == 4
    )

    recent_session = RecordingSession(_ScalarsResult([challenge]))
    assert await FriendChallengesRepo.list_recent_for_user(
        recent_session,
        user_id=10,
        limit=0,
    ) == [challenge]
    recent_sql = compile_statement(recent_session.statement)
    assert "ORDER BY friend_challenges.created_at DESC" in recent_sql
    assert "LIMIT 1" in recent_sql

    last_chance_session = RecordingSession(_ScalarsResult([challenge]))
    await FriendChallengesRepo.list_active_due_for_last_chance_for_update(
        last_chance_session,
        now_utc=now_utc,
        expires_before_utc=now_utc,
        limit=0,
    )
    last_chance_sql = compile_statement(last_chance_session.statement)
    assert "FOR UPDATE SKIP LOCKED" in last_chance_sql
    assert "friend_challenges.expires_last_chance_notified_at IS NULL" in last_chance_sql
    assert (
        "friend_challenges.status IN "
        "('PENDING', 'ACCEPTED', 'CREATOR_DONE', 'OPPONENT_DONE', 'ACTIVE')" in last_chance_sql
    )

    active_expire_session = RecordingSession(_ScalarsResult([challenge]))
    await FriendChallengesRepo.list_active_due_for_expire_for_update(
        active_expire_session,
        now_utc=now_utc,
        limit=2,
    )
    assert "friend_challenges.expires_at <=" in compile_statement(active_expire_session.statement)

    pending_expire_session = RecordingSession(_ScalarsResult([challenge]))
    await FriendChallengesRepo.list_pending_due_for_expire_for_update(
        pending_expire_session,
        now_utc=now_utc,
        limit=2,
    )
    assert "friend_challenges.status = 'PENDING'" in compile_statement(
        pending_expire_session.statement
    )

    walkover_session = RecordingSession(_ScalarsResult([challenge]))
    await FriendChallengesRepo.list_joined_due_for_walkover_for_update(
        walkover_session,
        now_utc=now_utc,
        limit=2,
    )
    assert "friend_challenges.opponent_user_id IS NOT NULL" in compile_statement(
        walkover_session.statement
    )

    series_session = RecordingSession(_ScalarsResult([challenge]))
    await FriendChallengesRepo.list_by_series_id_for_update(series_session, series_id=uuid4())
    series_sql = compile_statement(series_session.statement)
    assert "ORDER BY friend_challenges.series_game_number ASC" in series_sql
    assert "FOR UPDATE" in series_sql
