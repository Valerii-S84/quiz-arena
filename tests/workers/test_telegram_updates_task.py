import asyncio

from app.workers.tasks import telegram_updates


def test_process_telegram_update_returns_ignored_when_update_id_missing() -> None:
    result = telegram_updates.process_telegram_update(update_payload={"message": {"message_id": 1}})
    assert result == "ignored"


def test_process_telegram_update_uses_extracted_update_id(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_process_update_async(
        update_payload: dict[str, object],
        *,
        update_id: int,
        task_id: str | None = None,
    ) -> str:
        captured["update_payload"] = update_payload
        captured["update_id"] = update_id
        captured["task_id"] = task_id
        return "processed"

    monkeypatch.setattr(telegram_updates, "process_update_async", fake_process_update_async)

    result = telegram_updates.process_telegram_update(update_payload={"update_id": 777})
    assert result == "processed"
    assert captured["update_id"] == 777


def test_process_telegram_update_prefers_explicit_update_id(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_process_update_async(
        update_payload: dict[str, object],
        *,
        update_id: int,
        task_id: str | None = None,
    ) -> str:
        captured["update_id"] = update_id
        captured["task_id"] = task_id
        return "processed"

    monkeypatch.setattr(telegram_updates, "process_update_async", fake_process_update_async)

    result = telegram_updates.process_telegram_update(
        update_payload={"update_id": 777},
        update_id=888,
    )
    assert result == "processed"
    assert captured["update_id"] == 888


def test_acquire_processing_slot_returns_created(monkeypatch) -> None:
    async def fake_try_create_processing_slot(*args, **kwargs) -> bool:
        _ = (args, kwargs)
        return True

    async def fake_false(*args, **kwargs) -> bool:
        _ = (args, kwargs)
        return False

    monkeypatch.setattr(
        telegram_updates.ProcessedUpdatesRepo,
        "try_create_processing_slot",
        fake_try_create_processing_slot,
    )
    monkeypatch.setattr(
        telegram_updates.ProcessedUpdatesRepo,
        "try_reclaim_failed_processing_slot",
        fake_false,
    )
    monkeypatch.setattr(
        telegram_updates.ProcessedUpdatesRepo,
        "try_reclaim_stale_processing_slot",
        fake_false,
    )

    outcome = asyncio.run(
        telegram_updates._acquire_processing_slot(
            777,
            task_id="task-1",
            processing_ttl_seconds=300,
        )
    )
    assert outcome == "created"


def test_acquire_processing_slot_returns_reclaimed_stale(monkeypatch) -> None:
    async def fake_false(*args, **kwargs) -> bool:
        _ = (args, kwargs)
        return False

    async def fake_true(*args, **kwargs) -> bool:
        _ = (args, kwargs)
        return True

    monkeypatch.setattr(
        telegram_updates.ProcessedUpdatesRepo, "try_create_processing_slot", fake_false
    )
    monkeypatch.setattr(
        telegram_updates.ProcessedUpdatesRepo,
        "try_reclaim_failed_processing_slot",
        fake_false,
    )
    monkeypatch.setattr(
        telegram_updates.ProcessedUpdatesRepo,
        "try_reclaim_stale_processing_slot",
        fake_true,
    )

    outcome = asyncio.run(
        telegram_updates._acquire_processing_slot(
            777,
            task_id="task-1",
            processing_ttl_seconds=300,
        )
    )
    assert outcome == "reclaimed_stale"


def test_acquire_processing_slot_returns_duplicate(monkeypatch) -> None:
    async def fake_false(*args, **kwargs) -> bool:
        _ = (args, kwargs)
        return False

    monkeypatch.setattr(
        telegram_updates.ProcessedUpdatesRepo, "try_create_processing_slot", fake_false
    )
    monkeypatch.setattr(
        telegram_updates.ProcessedUpdatesRepo,
        "try_reclaim_failed_processing_slot",
        fake_false,
    )
    monkeypatch.setattr(
        telegram_updates.ProcessedUpdatesRepo,
        "try_reclaim_stale_processing_slot",
        fake_false,
    )

    outcome = asyncio.run(
        telegram_updates._acquire_processing_slot(
            777,
            task_id="task-1",
            processing_ttl_seconds=300,
        )
    )
    assert outcome == "duplicate"


def test_retry_backoff_seconds_honors_max(monkeypatch) -> None:
    monkeypatch.setattr(telegram_updates.random, "randint", lambda _a, _b: 0)
    backoff = telegram_updates._retry_backoff_seconds(
        next_retry_attempt=12,
        backoff_max_seconds=300,
    )
    assert backoff == 300


def test_telegram_update_task_retry_config_is_enabled() -> None:
    task = telegram_updates.process_telegram_update._get_current_object()

    assert task.max_retries == telegram_updates.TASK_MAX_RETRIES
    assert task.reject_on_worker_lost is True
    assert task.acks_late is True
