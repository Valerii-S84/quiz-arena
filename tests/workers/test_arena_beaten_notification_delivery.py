from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from app.game.arena_duels.constants import ARENA_BEATEN_NOTIFICATION_TYPE
from app.game.arena_duels.types import ArenaBeatenNotification
from app.services.telegram_delivery_outcomes import (
    TelegramDeliveryOutcome,
    TelegramDeliveryOutcomeStatus,
    TelegramDeliverySkip,
)
from app.workers.tasks import arena_duels_notification_delivery as delivery
from app.workers.tasks.arena_duels_notification_delivery_queries import ArenaBeatenNotificationDeps
from app.workers.tasks.arena_duels_notification_delivery_target import beaten_delivery_attempt
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


class _SessionLocal:
    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(object())


class _AnalyticsRepo:
    def __init__(self, events: list[str], *, existing: bool = False) -> None:
        self.events = events
        self.existing = existing
        self.fail_create = False

    async def lock_arena_beaten_notification_event_key(
        self,
        _session: object,
        **_kwargs: object,
    ) -> None:
        return None

    async def has_arena_beaten_notification_event(
        self,
        _session: object,
        **_kwargs: object,
    ) -> bool:
        return self.existing

    async def create_arena_beaten_notification_event_once(
        self,
        _session: object,
        **_kwargs: object,
    ) -> bool:
        self.events.append("analytics")
        if self.fail_create:
            raise RuntimeError("analytics write failed")
        self.existing = True
        return True


class _UsersRepo:
    def __init__(self, *, include_target: bool = True) -> None:
        self.include_target = include_target

    async def list_by_ids(
        self,
        _session: object,
        user_ids: list[int],
    ) -> list[object]:
        assert user_ids == [11, 22]
        users: list[object] = [
            SimpleNamespace(id=22, telegram_user_id=220_000_022, username="anna")
        ]
        if self.include_target:
            users.insert(0, SimpleNamespace(id=11, telegram_user_id=110_000_011))
        return users


class _Bot:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, object]] = []

    async def send_message(self, **kwargs: object) -> None:
        self.sent_messages.append(kwargs)


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


def _deps(
    events: list[str],
    *,
    existing: bool = False,
    include_target: bool = True,
) -> tuple[ArenaBeatenNotificationDeps, _AnalyticsRepo]:
    analytics = _AnalyticsRepo(events, existing=existing)
    return (
        ArenaBeatenNotificationDeps(
            session_local=_SessionLocal(),
            analytics_repo=analytics,
            users_repo=_UsersRepo(include_target=include_target),
        ),
        analytics,
    )


def _outcome(
    status: TelegramDeliveryOutcomeStatus,
    *,
    attempted: bool,
    replayed: bool = False,
    failure_code: str | None = None,
) -> TelegramDeliveryOutcome:
    return TelegramDeliveryOutcome(
        status=status,
        created=not replayed,
        attempted=attempted,
        replayed=replayed,
        failure_code=failure_code,
    )


async def test_stable_target_and_success_persist_sent_before_analytics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    deps, _analytics = _deps(events)
    bot = _Bot()

    async def _deliver_once(_session_local: object, **kwargs: Any):
        attempt = kwargs["attempt"]
        assert attempt == beaten_delivery_attempt(
            notification=_notification(),
            telegram_user_id=110_000_011,
        )
        assert attempt.idempotency_key.endswith(":cccccccc-cccc-cccc-cccc-cccccccccccc:user:11")
        assert "pending_replay_safe" not in attempt.safe_context
        assert kwargs["allow_stale_pending_replay_send"] is True
        await kwargs["send"]()
        events.append("durable_sent")
        return _outcome("SENT", attempted=True)

    monkeypatch.setattr(delivery, "deliver_telegram_once", _deliver_once)

    result = await delivery.send_arena_beaten_notification_with_bot(
        bot=bot,
        notification=_notification(),
        happened_at=NOW_UTC,
        source="worker",
        deps=deps,
    )

    assert result == {"sent_total": 1, "failed_total": 0, "skipped_total": 0}
    assert events == ["durable_sent", "analytics"]
    assert bot.sent_messages[0]["chat_id"] == 110_000_011
    assert "@anna" in str(bot.sent_messages[0]["text"])


@pytest.mark.parametrize(
    ("existing", "include_target", "expected_code"),
    (
        (True, True, "DUPLICATE"),
        (False, False, "MISSING_TARGET_USER"),
    ),
)
async def test_duplicate_and_missing_target_are_durable_skips(
    monkeypatch: pytest.MonkeyPatch,
    existing: bool,
    include_target: bool,
    expected_code: str,
) -> None:
    deps, _analytics = _deps([], existing=existing, include_target=include_target)
    calls: list[TelegramDeliverySkip] = []

    async def _deliver_once(_session_local: object, **kwargs: Any):
        calls.append(kwargs["skip"])
        return _outcome("SKIPPED", attempted=False, failure_code=expected_code)

    monkeypatch.setattr(delivery, "deliver_telegram_once", _deliver_once)

    result = await delivery.send_arena_beaten_notification_with_bot(
        bot=_Bot(),
        notification=_notification(),
        happened_at=NOW_UTC,
        source="worker",
        deps=deps,
    )

    assert result == {"sent_total": 0, "failed_total": 0, "skipped_total": 1}
    assert calls[0].failure_code == expected_code


@pytest.mark.parametrize(
    ("outcome", "expected"),
    (
        (
            _outcome("FAILED", attempted=True, failure_code="TELEGRAM_FORBIDDEN"),
            {"sent_total": 0, "failed_total": 1, "skipped_total": 0},
        ),
        (
            _outcome("RETRY", attempted=True),
            {"sent_total": 0, "failed_total": 1, "skipped_total": 0},
        ),
        (
            _outcome(
                "SKIPPED",
                attempted=False,
                failure_code="TELEGRAM_BLOCKED_CANDIDATE",
            ),
            {"sent_total": 0, "failed_total": 0, "skipped_total": 1},
        ),
    ),
)
async def test_telegram_failure_retry_and_blocked_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    outcome: TelegramDeliveryOutcome,
    expected: dict[str, int],
) -> None:
    events: list[str] = []
    deps, _analytics = _deps(events)

    async def _deliver_once(_session_local: object, **_kwargs: Any):
        return outcome

    monkeypatch.setattr(delivery, "deliver_telegram_once", _deliver_once)

    result = await delivery.send_arena_beaten_notification_with_bot(
        bot=_Bot(),
        notification=_notification(),
        happened_at=NOW_UTC,
        source="worker",
        deps=deps,
    )

    assert result == expected
    assert events == []


async def test_terminal_persistence_failure_leaves_replay_unsent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    deps, _analytics = _deps(events)
    bot = _Bot()
    calls = 0

    async def _deliver_once(_session_local: object, **kwargs: Any):
        nonlocal calls
        calls += 1
        if calls == 1:
            await kwargs["send"]()
            raise RuntimeError("telegram delivery sent lease was lost")
        return _outcome("RETRY", attempted=False, replayed=True)

    monkeypatch.setattr(delivery, "deliver_telegram_once", _deliver_once)

    with pytest.raises(RuntimeError, match="sent lease was lost"):
        await delivery.send_arena_beaten_notification_with_bot(
            bot=bot,
            notification=_notification(),
            happened_at=NOW_UTC,
            source="worker",
            deps=deps,
        )
    replay = await delivery.send_arena_beaten_notification_with_bot(
        bot=bot,
        notification=_notification(),
        happened_at=NOW_UTC,
        source="worker",
        deps=deps,
    )

    assert replay == {"sent_total": 0, "failed_total": 1, "skipped_total": 0}
    assert len(bot.sent_messages) == 1
    assert events == []


async def test_analytics_failure_after_durable_sent_does_not_duplicate_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    deps, analytics = _deps(events)
    analytics.fail_create = True
    bot = _Bot()
    delivery_sent = False

    async def _deliver_once(_session_local: object, **kwargs: Any):
        nonlocal delivery_sent
        if delivery_sent:
            return _outcome("SENT", attempted=False, replayed=True)
        await kwargs["send"]()
        delivery_sent = True
        return _outcome("SENT", attempted=True)

    monkeypatch.setattr(delivery, "deliver_telegram_once", _deliver_once)

    for _attempt in range(2):
        with pytest.raises(RuntimeError, match="analytics write failed"):
            await delivery.send_arena_beaten_notification_with_bot(
                bot=bot,
                notification=_notification(),
                happened_at=NOW_UTC,
                source="worker",
                deps=deps,
            )

    assert delivery_sent is True
    assert len(bot.sent_messages) == 1
    assert events == ["analytics", "analytics"]
