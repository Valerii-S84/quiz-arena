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
