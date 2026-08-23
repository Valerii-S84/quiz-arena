from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from alembic import op


class _AuthorityMigration(Protocol):
    def _backfill_admin_authority(
        self,
        bind: Connection,
        *,
        bootstrap_email: str,
        bootstrap_role: str,
    ) -> None: ...

    def upgrade(self) -> None: ...

    def downgrade(self) -> None: ...


def _load_migration() -> _AuthorityMigration:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "e8f9a0b1c234_m59_add_admin_enabled_authority.py"
    )
    spec = importlib.util.spec_from_file_location("test_admin_authority_migration", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(_AuthorityMigration, module)


def _database() -> tuple[Engine, sa.Table]:
    metadata = sa.MetaData()
    admins = sa.Table(
        "admins",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(100), nullable=False, unique=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return engine, admins


def _admin_values(
    *,
    email: str,
    role: str = "super_admin",
    enabled: bool = False,
) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    return {
        "id": uuid4(),
        "email": email,
        "role": role,
        "enabled": enabled,
        "created_at": now,
        "updated_at": now,
    }


def test_backfill_enables_only_configured_admin_and_preserves_existing_role() -> None:
    migration = _load_migration()
    engine, admins = _database()
    with engine.begin() as bind:
        bind.execute(
            admins.insert(),
            [
                _admin_values(email=" Admin@Example.com "),
                _admin_values(email="other@example.com", enabled=True),
            ],
        )
        migration._backfill_admin_authority(
            bind,
            bootstrap_email="ADMIN@example.com",
            bootstrap_role="admin",
        )

    with engine.connect() as bind:
        rows = {
            row.email: row for row in bind.execute(sa.select(admins).order_by(admins.c.email)).all()
        }
    assert rows["admin@example.com"].role == "super_admin"
    assert rows["admin@example.com"].enabled is True
    assert rows["other@example.com"].enabled is False


def test_backfill_bootstraps_first_admin_only_when_table_is_empty() -> None:
    migration = _load_migration()
    engine, admins = _database()
    with engine.begin() as bind:
        migration._backfill_admin_authority(
            bind,
            bootstrap_email="admin@example.com",
            bootstrap_role="super-admin",
        )

    with engine.connect() as bind:
        row = bind.execute(sa.select(admins)).one()
    assert row.email == "admin@example.com"
    assert row.role == "super_admin"
    assert row.enabled is True


def test_backfill_rejects_missing_configured_identity_in_nonempty_table() -> None:
    migration = _load_migration()
    engine, admins = _database()
    with engine.begin() as bind:
        bind.execute(
            admins.insert().values(**_admin_values(email="other@example.com", enabled=True))
        )

    with pytest.raises(RuntimeError, match="identity is missing"):
        with engine.begin() as bind:
            migration._backfill_admin_authority(
                bind,
                bootstrap_email="admin@example.com",
                bootstrap_role="admin",
            )

    with engine.connect() as bind:
        row = bind.execute(sa.select(admins)).one()
    assert row.email == "other@example.com"
    assert row.enabled is True


def test_backfill_rejects_normalized_duplicate_without_merging() -> None:
    migration = _load_migration()
    engine, admins = _database()
    with engine.begin() as bind:
        bind.execute(
            admins.insert(),
            [
                _admin_values(email="admin@example.com"),
                _admin_values(email=" ADMIN@example.com "),
            ],
        )

    with pytest.raises(RuntimeError, match="identity is duplicated"):
        with engine.begin() as bind:
            migration._backfill_admin_authority(
                bind,
                bootstrap_email="admin@example.com",
                bootstrap_role="admin",
            )

    with engine.connect() as bind:
        rows = bind.execute(sa.select(admins)).all()
    assert len(rows) == 2
    assert all(row.enabled is False for row in rows)


def test_backfill_rejects_invalid_bootstrap_role_without_disabling_admins() -> None:
    migration = _load_migration()
    engine, admins = _database()
    with engine.begin() as bind:
        bind.execute(
            admins.insert().values(**_admin_values(email="admin@example.com", enabled=True))
        )

    with pytest.raises(RuntimeError, match="bootstrap role is invalid"):
        with engine.begin() as bind:
            migration._backfill_admin_authority(
                bind,
                bootstrap_email="admin@example.com",
                bootstrap_role="owner",
            )

    with engine.connect() as bind:
        row = bind.execute(sa.select(admins)).one()
    assert row.role == "super_admin"
    assert row.enabled is True


def test_upgrade_rejects_offline_mode_before_emitting_schema_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    calls: list[str] = []
    context = type("OfflineContext", (), {"as_sql": True})()
    monkeypatch.setattr(op, "get_context", lambda: context)
    monkeypatch.setattr(op, "add_column", lambda *args, **kwargs: calls.append("add_column"))

    with pytest.raises(RuntimeError, match="requires an online database connection"):
        migration.upgrade()

    assert calls == []


def test_downgrade_is_blocked_to_preserve_database_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    calls: list[str] = []
    monkeypatch.setattr(op, "drop_column", lambda *args, **kwargs: calls.append("drop_column"))

    with pytest.raises(RuntimeError, match="security-critical and forward-only"):
        migration.downgrade()

    assert calls == []
