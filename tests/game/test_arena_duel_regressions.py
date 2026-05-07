from __future__ import annotations

from tests.game.arena_duel_regressions_support import AnalyticsEvent, ArenaDuel, Path, Table, cast


def test_arena_baseline_fk_requires_same_duel_in_model_and_migration() -> None:
    duel_table = cast(Table, ArenaDuel.__table__)
    fk = next(
        constraint
        for constraint in duel_table.foreign_key_constraints
        if constraint.name == "fk_arena_duels_baseline_attempt_id_arena_attempts"
    )
    migration = Path("alembic/versions/f7a8b9c0d1e2_m47_open_arena_foundation.py").read_text()

    assert [column.name for column in fk.columns] == ["id", "baseline_attempt_id"]
    assert [f"{element.column.table.name}.{element.column.name}" for element in fk.elements] == [
        "arena_attempts.arena_duel_id",
        "arena_attempts.id",
    ]
    assert '"uq_arena_attempts_duel_id_id"' in migration
    assert '["id", "baseline_attempt_id"]' in migration
    assert '["arena_duel_id", "id"]' in migration


def test_arena_beaten_notification_dedupe_index_matches_migration() -> None:
    analytics_table = cast(Table, AnalyticsEvent.__table__)
    index = next(
        db_index
        for db_index in analytics_table.indexes
        if db_index.name == "uq_analytics_events_arena_beaten_notice_once"
    )
    migration = Path(
        "alembic/versions/f8a9b0c1d2e3_m48_arena_beaten_notification_dedupe.py"
    ).read_text()

    assert index.unique is True
    assert "payload ->> 'arena_duel_id'" in migration
    assert "payload ->> 'previous_best_attempt_id'" in migration
    assert "payload ->> 'new_best_attempt_id'" in migration
    assert "payload ->> 'notification_type'" in migration
    assert "arena_result_beaten_notification_sent" in migration


def test_arena_revanche_dedupe_index_matches_migration() -> None:
    analytics_table = cast(Table, AnalyticsEvent.__table__)
    index = next(
        db_index
        for db_index in analytics_table.indexes
        if db_index.name == "uq_analytics_events_arena_revanche_once"
    )
    migration = Path("alembic/versions/c0d1e2f3a4b5_m51_arena_revanche_dedupe.py").read_text()

    assert index.unique is True
    assert "payload ->> 'revanche_receiver_id'" in migration
    assert "payload ->> 'source_attempt_id'" in migration
    assert "payload ->> 'notification_type'" in migration
    assert "arena_revanche_sent" in migration


def test_arena_access_type_constraints_match_migration() -> None:
    migration = Path("alembic/versions/a9b0c1d2e3f4_m49_arena_duel_access_type.py").read_text()

    assert "ck_arena_duels_access_type" in migration
    assert "ck_arena_attempts_access_type" in migration
    assert "access_type IN ('FREE','PAID_TICKET','PREMIUM')" in migration
    assert 'server_default="FREE"' in migration


def test_arena_source_friend_unique_migration_is_fail_fast_and_non_destructive() -> None:
    migration = Path("alembic/versions/b0c1d2e3f4a5_m50_arena_source_friend_unique.py").read_text()

    assert "uq_arena_duels_source_friend_once" in migration
    assert "GROUP BY source_friend_challenge_id" in migration
    assert "HAVING COUNT(*) > 1" in migration
    assert "RAISE EXCEPTION" in migration
    assert "approved maintenance flow" in migration
    assert "source_friend_challenge_id IS NOT NULL" in migration
    assert "unique=True" in migration
    assert "row_number() OVER" not in migration
    assert "PARTITION BY source_friend_challenge_id" not in migration
    assert "source_friend_challenge_id = NULL" not in migration
