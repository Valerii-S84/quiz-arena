from __future__ import annotations

import pytest

from app.workers.tasks import premium_expiry
from tests.type_helpers import AsyncBeginContext


class _SessionLocal:
    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(object())


@pytest.mark.asyncio
async def test_expire_premium_entitlements_async_marks_expired_active_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def _count(_session, **kwargs) -> int:
        calls.append(("count", kwargs))
        return 3

    async def _expire(_session, **kwargs) -> int:
        calls.append(("expire", kwargs))
        return 2

    monkeypatch.setattr(premium_expiry, "SessionLocal", _SessionLocal())
    monkeypatch.setattr(premium_expiry.EntitlementsRepo, "count_expired_active_premium", _count)
    monkeypatch.setattr(premium_expiry.EntitlementsRepo, "expire_active_premium_before", _expire)

    result = await premium_expiry.expire_premium_entitlements_async(batch_size=2)

    assert result == {
        "expired_active_before": 3,
        "expired_total": 2,
        "expired_active_remaining": 1,
    }
    assert calls[1][1]["limit"] == 2


def test_expire_premium_entitlements_task_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _run_tracked(**kwargs):
        captured.update(kwargs)
        kwargs["awaitable"].close()
        return {"expired_total": 1}

    monkeypatch.setattr(premium_expiry, "run_tracked_async_job", _run_tracked)

    result = premium_expiry.expire_premium_entitlements(batch_size=50)

    assert result == {"expired_total": 1}
    assert captured["task_name"] == premium_expiry.TASK_NAME
    assert captured["schedule_key"] == premium_expiry.SCHEDULE_KEY


def test_premium_expiry_schedule_registered() -> None:
    schedule = premium_expiry.celery_app.conf.beat_schedule[premium_expiry.SCHEDULE_KEY]

    assert schedule == {
        "task": premium_expiry.TASK_NAME,
        "schedule": 3600.0,
        "options": {"queue": "q_normal"},
    }
