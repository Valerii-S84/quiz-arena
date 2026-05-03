from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from app.workers.tasks import arena_duels, arena_duels_schedule
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)


class _SessionLocal:
    def __init__(self, session: object) -> None:
        self._session = session

    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(self._session)


def test_expire_arena_duels_returns_active_and_draft_counters(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    async def _fake_expire_active(session, *, now_utc):
        calls.append({"kind": "active", "session": session, "now_utc": now_utc})
        return 2

    async def _fake_expire_draft(session, *, now_utc):
        calls.append({"kind": "draft", "session": session, "now_utc": now_utc})
        return 1

    session = object()
    monkeypatch.setattr(arena_duels, "SessionLocal", _SessionLocal(session))
    monkeypatch.setattr(arena_duels.ArenaDuelsRepo, "expire_active_duels", _fake_expire_active)
    monkeypatch.setattr(arena_duels.ArenaDuelsRepo, "expire_draft_duels", _fake_expire_draft)

    result = asyncio.run(arena_duels.expire_arena_duels(now_utc=NOW_UTC))

    assert result == {"expired_active_total": 2, "expired_draft_total": 1}
    assert calls == [
        {"kind": "active", "session": session, "now_utc": NOW_UTC},
        {"kind": "draft", "session": session, "now_utc": NOW_UTC},
    ]


def test_configure_arena_duels_schedule_registers_expiry_task() -> None:
    celery_app = SimpleNamespace(conf=SimpleNamespace(beat_schedule={}))

    arena_duels_schedule.configure_arena_duels_schedule(celery_app)

    schedule = celery_app.conf.beat_schedule
    assert schedule["arena-duel-expiry-every-5-minutes"] == {
        "task": "app.workers.tasks.arena_duels.expire_arena_duels",
        "schedule": 300.0,
        "options": {"queue": "q_normal"},
    }
