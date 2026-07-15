from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Iterator


class _MigrationContext:
    def __init__(self, events: list[tuple[object, ...]]) -> None:
        self.events = events

    @contextmanager
    def autocommit_block(self) -> Iterator[None]:
        self.events.append(("autocommit_enter",))
        try:
            yield
        finally:
            self.events.append(("autocommit_exit",))


class _MigrationOperations:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []
        self.context = _MigrationContext(self.events)

    def get_context(self) -> _MigrationContext:
        return self.context

    def execute(self, statement: str) -> None:
        self.events.append(("execute", statement))

    def create_index(self, name: str, table_name: str, columns: list[str]) -> None:
        self.events.append(("create_index", name, table_name, columns))

    def drop_index(self, name: str, *, table_name: str) -> None:
        self.events.append(("drop_index", name, table_name))


def _load_m57() -> ModuleType:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "c7d8e9f0a1b3_m57_delivery_query_indexes.py"
    )
    spec = importlib.util.spec_from_file_location("m57_delivery_query_indexes", migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_m57_upgrade_creates_quiz_attempts_index_concurrently_in_autocommit() -> None:
    migration = _load_m57()
    operations = _MigrationOperations()
    setattr(migration, "op", operations)

    migration.upgrade()

    assert operations.events == [
        (
            "create_index",
            "idx_telegram_delivery_status_updated_at",
            "telegram_delivery_attempts",
            ["status", "updated_at"],
        ),
        ("autocommit_enter",),
        (
            "execute",
            "CREATE INDEX CONCURRENTLY idx_attempts_answered_at_user "
            "ON quiz_attempts (answered_at, user_id)",
        ),
        ("autocommit_exit",),
    ]


def test_m57_downgrade_drops_quiz_attempts_index_concurrently_in_autocommit() -> None:
    migration = _load_m57()
    operations = _MigrationOperations()
    setattr(migration, "op", operations)

    migration.downgrade()

    assert operations.events == [
        ("autocommit_enter",),
        ("execute", "DROP INDEX CONCURRENTLY idx_attempts_answered_at_user"),
        ("autocommit_exit",),
        (
            "drop_index",
            "idx_telegram_delivery_status_updated_at",
            "telegram_delivery_attempts",
        ),
    ]
