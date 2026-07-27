from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main as app_main


def _settings(*, enable_openapi_docs: bool, app_env: str = "test") -> SimpleNamespace:
    return SimpleNamespace(
        log_level="INFO",
        enable_openapi_docs=enable_openapi_docs,
        app_env=app_env,
    )


def test_openapi_docs_enabled(monkeypatch) -> None:
    monkeypatch.setattr(app_main, "get_settings", lambda: _settings(enable_openapi_docs=True))
    client = TestClient(app_main.create_app())

    docs_response = client.get("/docs")
    redoc_response = client.get("/redoc")
    openapi_response = client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert redoc_response.status_code == 200
    assert openapi_response.status_code == 200


def test_openapi_docs_disabled(monkeypatch) -> None:
    monkeypatch.setattr(app_main, "get_settings", lambda: _settings(enable_openapi_docs=False))
    client = TestClient(app_main.create_app())

    docs_response = client.get("/docs")
    redoc_response = client.get("/redoc")
    openapi_response = client.get("/openapi.json")

    assert docs_response.status_code == 404
    assert redoc_response.status_code == 404
    assert openapi_response.status_code == 404


@pytest.mark.parametrize(
    ("app_env", "expected_started"),
    [("production", True), ("test", False)],
)
async def test_lifespan_starts_monitor_only_in_production(
    monkeypatch,
    app_env: str,
    expected_started: bool,
) -> None:
    started = asyncio.Event()

    async def _monitor() -> None:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(
        app_main,
        "get_settings",
        lambda: _settings(enable_openapi_docs=False, app_env=app_env),
    )
    monkeypatch.setattr(app_main, "run_production_invariant_monitor", _monitor)

    async with app_main.app_lifespan(app_main.create_app()):
        await asyncio.sleep(0)
        assert started.is_set() is expected_started
