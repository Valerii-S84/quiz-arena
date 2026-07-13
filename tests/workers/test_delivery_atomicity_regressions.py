from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.game.arena_duels.constants import ARENA_BEATEN_NOTIFICATION_TYPE
from app.game.arena_duels.types import ArenaBeatenNotification
from app.workers.tasks import arena_duels_notification_delivery as arena_delivery
from app.workers.tasks.arena_duels_notification_delivery_queries import ArenaBeatenNotificationDeps

NOW_UTC = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


class _RollbackContext:
    def __init__(self, state: dict[str, object], session: object) -> None:
        self.state = state
        self.session = session

    async def __aenter__(self) -> object:
        self.snapshot = dict(self.state)
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.state.clear()
            self.state.update(self.snapshot)
        return False


class _RollbackSessionLocal:
    def __init__(self, state: dict[str, object], session: object) -> None:
        self.state = state
        self.session = session

    def begin(self) -> _RollbackContext:
        return _RollbackContext(self.state, self.session)


def _notification() -> ArenaBeatenNotification:
    return ArenaBeatenNotification(
        arena_duel_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        previous_best_attempt_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        previous_best_user_id=11,
        previous_best_score=6,
        previous_best_time_ms=48_000,
        new_best_attempt_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        new_best_user_id=22,
        new_best_score=7,
        new_best_time_ms=52_000,
        notification_type=ARENA_BEATEN_NOTIFICATION_TYPE,
    )


async def test_arena_sent_outcome_rolls_back_when_analytics_write_fails(monkeypatch) -> None:
    state: dict[str, object] = {"delivery": "PENDING", "analytics": False}
    session = object()

    async def _lock(_session, **_kwargs) -> None:
        return None

    async def _has_event(_session, **_kwargs) -> bool:
        return False

    async def _users(_session, _user_ids):
        return [
            SimpleNamespace(id=11, telegram_user_id=110_000_011),
            SimpleNamespace(id=22, telegram_user_id=220_000_022, username="anna"),
        ]

    async def _prepare(**kwargs):
        return SimpleNamespace(
            should_send=True,
            idempotency_key=kwargs["target"].idempotency_key,
        )

    async def _sent(**kwargs) -> None:
        assert kwargs["session"] is session
        state["delivery"] = "SENT"

    async def _analytics(_session, **_kwargs) -> bool:
        assert _session is session
        raise RuntimeError("analytics write failed")

    async def _send(*_args, **_kwargs) -> None:
        return None

    deps = ArenaBeatenNotificationDeps(
        session_local=_RollbackSessionLocal(state, session),
        analytics_repo=SimpleNamespace(
            lock_arena_beaten_notification_event_key=_lock,
            has_arena_beaten_notification_event=_has_event,
            create_arena_beaten_notification_event_once=_analytics,
        ),
        users_repo=SimpleNamespace(list_by_ids=_users),
    )
    monkeypatch.setattr(arena_delivery, "prepare_telegram_delivery", _prepare)
    monkeypatch.setattr(arena_delivery, "mark_telegram_delivery_sent", _sent)
    monkeypatch.setattr(arena_delivery, "_send_notification_message", _send)

    with pytest.raises(RuntimeError, match="analytics write failed"):
        await arena_delivery.send_arena_beaten_notification_with_bot(
            bot=object(),
            notification=_notification(),
            happened_at=NOW_UTC,
            source="bot",
            deps=deps,
        )

    assert state == {"delivery": "PENDING", "analytics": False}
