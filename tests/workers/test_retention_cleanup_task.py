from app.workers.tasks import retention_cleanup


def test_run_retention_cleanup_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, object]:
        return {"rows_deleted_total": 7, "error_count": 0}

    monkeypatch.setattr(retention_cleanup, "run_retention_cleanup_async", fake_async)

    result = retention_cleanup.run_retention_cleanup()
    assert result == {"rows_deleted_total": 7, "error_count": 0}
