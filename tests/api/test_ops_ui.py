from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import ops_ui
from app.main import app


def _settings(*, allowlist: str = "127.0.0.1/32") -> SimpleNamespace:
    return SimpleNamespace(
        app_env="dev",
        internal_api_token="internal-secret",
        internal_api_allowlist=allowlist,
        internal_api_trusted_proxies="127.0.0.1/32",
    )


def test_ops_root_redirects_to_promo() -> None:
    client = TestClient(app)
    response = client.get("/ops", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/ops/promo"


def test_ops_promo_page_is_served_for_allowed_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_ui,
        "get_settings",
        lambda: _settings(),
    )

    client = TestClient(app, client=("127.0.0.1", 5100))
    response = client.get(
        "/ops/promo",
        headers={
            "X-Forwarded-For": "127.0.0.1",
            "X-Internal-Token": "internal-secret",
        },
    )

    assert response.status_code == 200
    assert "Promo Ops Console" in response.text


def test_ops_page_redirects_to_login_when_token_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_ui,
        "get_settings",
        lambda: _settings(),
    )

    client = TestClient(app, client=("127.0.0.1", 5103))
    response = client.get(
        "/ops/promo", headers={"X-Forwarded-For": "127.0.0.1"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/ops/login"


def test_ops_login_creates_session_cookie(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_ui,
        "get_settings",
        lambda: _settings(),
    )

    client = TestClient(app, client=("127.0.0.1", 5104))
    login = client.post(
        "/ops/login",
        data={"token": "internal-secret"},
        headers={
            "X-Forwarded-For": "127.0.0.1",
            "Origin": "http://testserver",
        },
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/ops/promo"

    response = client.get("/ops/promo", headers={"X-Forwarded-For": "127.0.0.1"})
    assert response.status_code == 200
    assert "Promo Ops Console" in response.text


def test_ops_login_rejects_cross_origin_post(monkeypatch) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 5105))
    response = client.post(
        "/ops/login",
        data={"token": "internal-secret"},
        headers={
            "X-Forwarded-For": "127.0.0.1",
            "Origin": "https://evil.example",
        },
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_ops_login_rejects_non_form_content_type(monkeypatch) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 5106))
    response = client.post(
        "/ops/login",
        json={"token": "internal-secret"},
        headers={
            "X-Forwarded-For": "127.0.0.1",
            "Origin": "http://testserver",
        },
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_ops_login_rate_limits_failed_attempts(monkeypatch) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())
    monkeypatch.setattr(ops_ui, "OPS_UI_LOGIN_MAX_FAILED_ATTEMPTS", 2)
    monkeypatch.setattr(ops_ui, "OPS_UI_LOGIN_FAILURE_DELAY_SECONDS", 0.0)
    ops_ui._LOGIN_FAILED_ATTEMPTS.clear()

    client = TestClient(app, client=("127.0.0.1", 5107))
    headers = {
        "X-Forwarded-For": "127.0.0.1",
        "Origin": "http://testserver",
    }

    first = client.post(
        "/ops/login", data={"token": "wrong-1"}, headers=headers, follow_redirects=False
    )
    second = client.post(
        "/ops/login", data={"token": "wrong-2"}, headers=headers, follow_redirects=False
    )
    third = client.post(
        "/ops/login",
        data={"token": "internal-secret"},
        headers=headers,
        follow_redirects=False,
    )
    ops_ui._LOGIN_FAILED_ATTEMPTS.clear()

    assert first.status_code == 403
    assert second.status_code == 403
    assert third.status_code == 429
    assert third.json() == {"detail": {"code": "E_RATE_LIMITED"}}


def test_ops_logout_rejects_cross_origin_post(monkeypatch) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 5108))
    login = client.post(
        "/ops/login",
        data={"token": "internal-secret"},
        headers={
            "X-Forwarded-For": "127.0.0.1",
            "Origin": "http://testserver",
        },
        follow_redirects=False,
    )
    assert login.status_code == 303

    logout = client.post(
        "/ops/logout",
        data={},
        headers={
            "X-Forwarded-For": "127.0.0.1",
            "Origin": "https://evil.example",
        },
        follow_redirects=False,
    )
    assert logout.status_code == 403
    assert logout.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_ops_logout_get_is_not_allowed(monkeypatch) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())
    client = TestClient(app, client=("127.0.0.1", 5109))
    response = client.get(
        "/ops/logout", headers={"X-Forwarded-For": "127.0.0.1"}, follow_redirects=False
    )

    assert response.status_code == 405


def test_ops_page_rejects_disallowed_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_ui,
        "get_settings",
        lambda: _settings(allowlist="192.168.0.0/16"),
    )

    client = TestClient(app, client=("127.0.0.1", 5101))
    response = client.get("/ops/referrals", headers={"X-Forwarded-For": "10.0.0.7"})

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_ops_page_rejects_spoofed_forwarded_for_from_untrusted_proxy(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ops_ui,
        "get_settings",
        lambda: _settings(allowlist="10.0.0.0/8"),
    )

    client = TestClient(app, client=("198.51.100.10", 5102))
    response = client.get("/ops/referrals", headers={"X-Forwarded-For": "10.0.0.7"})

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}
