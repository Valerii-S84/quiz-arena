from app.workers.tasks import promo_maintenance


def test_run_promo_reservation_expiry_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, int]:
        return {"expired_redemptions": 3}

    monkeypatch.setattr(promo_maintenance, "run_promo_reservation_expiry_async", fake_async)

    result = promo_maintenance.run_promo_reservation_expiry()
    assert result["expired_redemptions"] == 3


def test_run_promo_campaign_status_rollover_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, int]:
        return {
            "expired_campaigns": 2,
            "depleted_campaigns": 1,
            "updated_campaigns": 3,
        }

    monkeypatch.setattr(promo_maintenance, "run_promo_campaign_status_rollover_async", fake_async)

    result = promo_maintenance.run_promo_campaign_status_rollover()
    assert result["updated_campaigns"] == 3


def test_run_promo_bruteforce_guard_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, int]:
        return {
            "abusive_hashes": 1,
            "paused_campaigns": 1,
        }

    monkeypatch.setattr(promo_maintenance, "run_promo_bruteforce_guard_async", fake_async)

    result = promo_maintenance.run_promo_bruteforce_guard()
    assert result["paused_campaigns"] == 1
