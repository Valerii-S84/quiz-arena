import asyncio

from app.workers.tasks import referrals


def test_run_referral_qualification_checks_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, batch_size: int) -> dict[str, int]:
        return {"examined": batch_size, "qualified": 2, "canceled": 1, "rejected_fraud": 0}

    monkeypatch.setattr(referrals, "run_referral_qualification_checks_async", fake_async)

    result = referrals.run_referral_qualification_checks(batch_size=7)
    assert result["examined"] == 7
    assert result["qualified"] == 2


def test_run_referral_reward_distribution_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, batch_size: int) -> dict[str, int]:
        return {"referrers_examined": batch_size, "rewards_granted": 1, "deferred_limit": 0}

    monkeypatch.setattr(referrals, "run_referral_reward_distribution_async", fake_async)

    result = referrals.run_referral_reward_distribution(batch_size=3)
    assert result["referrers_examined"] == 3
    assert result["rewards_granted"] == 1


def test_send_referral_reward_alerts_sends_milestone_and_reward_events(monkeypatch) -> None:
    events: list[str] = []
    recorded: list[tuple[str, bool]] = []

    async def fake_send_ops_alert(*, event: str, payload: dict[str, object]) -> bool:
        events.append(event)
        return True

    async def fake_record_event(*, event_type: str, payload: dict[str, int], sent: bool) -> None:
        recorded.append((event_type, sent))

    monkeypatch.setattr(referrals, "send_ops_alert", fake_send_ops_alert)
    monkeypatch.setattr(referrals, "_record_referral_reward_event", fake_record_event)

    result = asyncio.run(
        referrals._send_referral_reward_alerts(
            result={
                "referrers_examined": 1,
                "rewards_granted": 1,
                "deferred_limit": 0,
                "awaiting_choice": 2,
            }
        )
    )

    assert events == [
        "referral_reward_milestone_available",
        "referral_reward_granted",
    ]
    assert recorded == [
        ("referral_reward_milestone_available", True),
        ("referral_reward_granted", True),
    ]
    assert result == {
        "milestone_alert_sent": 1,
        "reward_alert_sent": 1,
    }
