from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main as app_main


def _settings(*, enable_openapi_docs: bool) -> SimpleNamespace:
    return SimpleNamespace(
        log_level="INFO",
        enable_openapi_docs=enable_openapi_docs,
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
