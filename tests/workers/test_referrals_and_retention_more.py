from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.workers.tasks import referrals, retention_cleanup
from tests.workers.daily_cup_turn_reminder_test_support import session_local_with_sessions


def test_referral_reward_distribution_runs_notifications_and_alerts(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    async def _distribution(session, **kwargs):
        calls.append(("distribution", session))
        assert kwargs["batch_size"] == 5
        return {"newly_notified": 2, "rewards_granted": 1}

    async def _ready(**_kwargs):
        calls.append(("ready", 1))
        return {"reward_user_notified": 2, "reward_user_notify_failed": 0}

    async def _alerts(**kwargs):
        calls.append(("alerts", kwargs["result"]["rewards_granted"]))
        return {"milestone_alert_sent": 1, "reward_alert_sent": 1}

    monkeypatch.setattr(referrals, "SessionLocal", session_local_with_sessions("session"))
    monkeypatch.setattr(referrals.ReferralService, "run_reward_distribution", _distribution)
    monkeypatch.setattr(referrals, "_send_referral_ready_notifications", _ready)
    monkeypatch.setattr(referrals, "_send_referral_reward_alerts", _alerts)
    monkeypatch.setattr(referrals, "logger", SimpleNamespace(info=lambda *_args, **_kwargs: None))

    result = asyncio.run(referrals.run_referral_reward_distribution_async(batch_size=5))

    assert result["reward_user_notified"] == 2
    assert result["reward_alert_sent"] == 1
    assert calls == [("distribution", "session"), ("ready", 1), ("alerts", 1)]


def test_record_referral_reward_event_logs_failures(monkeypatch) -> None:
    exceptions: list[str] = []

    class _BadSessionLocal:
        def begin(self):
            raise RuntimeError("no db")

    monkeypatch.setattr(referrals, "SessionLocal", _BadSessionLocal())
    monkeypatch.setattr(
        referrals,
        "logger",
        SimpleNamespace(exception=lambda event, **_kwargs: exceptions.append(event)),
    )

    asyncio.run(
        referrals._record_referral_reward_event(event_type="evt", payload={"x": 1}, sent=False)
    )

    assert exceptions == ["referral_reward_event_record_failed"]


def test_retention_cleanup_async_and_task_wrapper(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    async def _run_tables(**kwargs):
        calls.append(("run", kwargs["config"]))
        return [{"table": "x"}], 3, 0

    monkeypatch.setattr(retention_cleanup, "get_settings", lambda: "settings")
    monkeypatch.setattr(
        retention_cleanup, "build_cleanup_config", lambda settings: {"settings": settings}
    )
    monkeypatch.setattr(retention_cleanup, "build_cleanup_table_specs", lambda **_kwargs: ["spec"])
    monkeypatch.setattr(retention_cleanup, "run_cleanup_tables", _run_tables)
    monkeypatch.setattr(
        retention_cleanup,
        "build_cleanup_result",
        lambda **kwargs: {
            "deleted": kwargs["total_rows_deleted"],
            "errors": kwargs["total_errors"],
        },
    )
    monkeypatch.setattr(
        retention_cleanup, "log_cleanup_result", lambda result: calls.append(("log", result))
    )
    monkeypatch.setattr(
        retention_cleanup, "run_async_job", lambda coro: (coro.close(), {"wrapped": True})[1]
    )

    assert asyncio.run(retention_cleanup.run_retention_cleanup_async()) == {
        "deleted": 3,
        "errors": 0,
    }
    assert retention_cleanup.run_retention_cleanup() == {"wrapped": True}
    assert calls == [("run", {"settings": "settings"}), ("log", {"deleted": 3, "errors": 0})]
