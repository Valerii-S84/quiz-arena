from __future__ import annotations

import hashlib
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import ops_ui
from app.main import app
from app.services import ops_auth
from app.services.internal_auth import OPS_UI_SESSION_COOKIE


class FakeOpsSessionRedis:
    def __init__(self) -> None:
        self._now = 0
        self._values: dict[str, tuple[str, int | None]] = {}

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        self._expire()
        if nx and key in self._values:
            return False
        self._values[key] = (value, self._now + ex)
        return True

    async def exists(self, key: str) -> int:
        self._expire()
        return int(key in self._values)

    async def delete(self, key: str) -> int:
        self._expire()
        return int(self._values.pop(key, None) is not None)

    def advance(self, seconds: int) -> None:
        self._now += seconds
        self._expire()

    def _expire(self) -> None:
        expired = [
            key
            for key, (_, expires_at) in self._values.items()
            if expires_at is not None and expires_at <= self._now
        ]
        for key in expired:
            self._values.pop(key, None)


def _settings(*, allowlist: str = "127.0.0.1/32") -> SimpleNamespace:
    return SimpleNamespace(
        app_env="dev",
        internal_api_token="internal-secret",
        internal_api_allowlist=allowlist,
        internal_api_trusted_proxies="127.0.0.1/32",
        redis_url="redis://unused-for-tests",
    )


def _trusted_headers(*, origin: str | None = None) -> dict[str, str]:
    headers = {"X-Forwarded-For": "127.0.0.1"}
    if origin is not None:
        headers["Origin"] = origin
    return headers


def _install_fake_ops_session_store(monkeypatch) -> FakeOpsSessionRedis:
    fake_redis = FakeOpsSessionRedis()

    async def _require_redis_client(settings):
        del settings
        return fake_redis

    monkeypatch.setattr(ops_auth, "_require_redis_client", _require_redis_client)
    return fake_redis


def test_ops_root_redirects_to_promo() -> None:
    client = TestClient(app)
    response = client.get("/ops", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/ops/promo"


def test_ops_page_redirects_to_login_when_only_internal_token_is_present(monkeypatch) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 5100))
    response = client.get(
        "/ops/promo",
        headers={
            "X-Forwarded-For": "127.0.0.1",
            "X-Internal-Token": "internal-secret",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/ops/login"


def test_ops_page_redirects_to_login_when_session_missing(monkeypatch) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 5103))
    response = client.get(
        "/ops/promo",
        headers={"X-Forwarded-For": "127.0.0.1"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/ops/login"


def test_ops_login_creates_opaque_session_cookie_and_allows_access(monkeypatch) -> None:
    fake_redis = _install_fake_ops_session_store(monkeypatch)
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 5104))
    login = client.post(
        "/ops/login",
        data={"token": "internal-secret"},
        headers=_trusted_headers(origin="http://testserver"),
        follow_redirects=False,
    )

    assert login.status_code == 303
    assert login.headers["location"] == "/ops/promo"

    session_cookie = login.cookies.get(OPS_UI_SESSION_COOKIE)
    assert session_cookie is not None
    assert session_cookie != hashlib.sha256(b"internal-secret").hexdigest()

    response = client.get("/ops/promo", headers=_trusted_headers())
    assert response.status_code == 200
    assert "Promo-Konsole" in response.text

    fake_redis.advance(1)
    assert session_cookie == client.cookies.get(OPS_UI_SESSION_COOKIE)


def test_ops_login_returns_503_when_session_state_is_unavailable(monkeypatch) -> None:
    async def _require_redis_client(settings):
        del settings
        raise ops_auth.OpsSessionStateError("down")

    monkeypatch.setattr(ops_auth, "_require_redis_client", _require_redis_client)
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 51041))
    response = client.post(
        "/ops/login",
        data={"token": "internal-secret"},
        headers=_trusted_headers(origin="http://testserver"),
        follow_redirects=False,
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


def test_ops_page_returns_503_when_session_state_is_unavailable(monkeypatch) -> None:
    async def _require_redis_client(settings):
        del settings
        raise ops_auth.OpsSessionStateError("down")

    monkeypatch.setattr(ops_auth, "_require_redis_client", _require_redis_client)
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 51042))
    client.cookies.set(OPS_UI_SESSION_COOKIE, "opaque-session")
    response = client.get("/ops/promo", headers=_trusted_headers(), follow_redirects=False)

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


def test_expired_ops_session_is_rejected(monkeypatch) -> None:
    fake_redis = _install_fake_ops_session_store(monkeypatch)
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 51043))
    login = client.post(
        "/ops/login",
        data={"token": "internal-secret"},
        headers=_trusted_headers(origin="http://testserver"),
        follow_redirects=False,
    )
    assert login.status_code == 303

    fake_redis.advance(ops_ui.OPS_UI_SESSION_MAX_AGE_SECONDS + 1)
    response = client.get("/ops/promo", headers=_trusted_headers(), follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ops/login"


def test_forged_ops_session_cookie_is_rejected(monkeypatch) -> None:
    _install_fake_ops_session_store(monkeypatch)
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 51044))
    client.cookies.set(OPS_UI_SESSION_COOKIE, "forged-session")
    response = client.get("/ops/promo", headers=_trusted_headers(), follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ops/login"


def test_replay_of_old_internal_token_hash_cookie_is_rejected(monkeypatch) -> None:
    _install_fake_ops_session_store(monkeypatch)
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 51045))
    client.cookies.set(OPS_UI_SESSION_COOKIE, hashlib.sha256(b"internal-secret").hexdigest())
    response = client.get("/ops/promo", headers=_trusted_headers(), follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ops/login"


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
        headers=_trusted_headers(origin="http://testserver"),
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
    headers = _trusted_headers(origin="http://testserver")

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


def test_ops_logout_revokes_server_side_session(monkeypatch) -> None:
    _install_fake_ops_session_store(monkeypatch)
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 5108))
    login = client.post(
        "/ops/login",
        data={"token": "internal-secret"},
        headers=_trusted_headers(origin="http://testserver"),
        follow_redirects=False,
    )
    assert login.status_code == 303
    captured_session = client.cookies.get(OPS_UI_SESSION_COOKIE)
    assert captured_session is not None

    logout = client.post(
        "/ops/logout",
        data={"logout": "1"},
        headers=_trusted_headers(origin="http://testserver"),
        follow_redirects=False,
    )
    assert logout.status_code == 303
    assert logout.headers["location"] == "/ops/login"

    client.cookies.set(OPS_UI_SESSION_COOKIE, captured_session)
    response = client.get("/ops/promo", headers=_trusted_headers(), follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/ops/login"


def test_ops_logout_returns_503_when_session_revocation_fails(monkeypatch) -> None:
    async def _require_redis_client(settings):
        del settings
        raise ops_auth.OpsSessionStateError("down")

    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())
    monkeypatch.setattr(ops_auth, "_require_redis_client", _require_redis_client)

    client = TestClient(app, client=("127.0.0.1", 51081))
    client.cookies.set(OPS_UI_SESSION_COOKIE, "opaque-session")
    response = client.post(
        "/ops/logout",
        data={"logout": "1"},
        headers=_trusted_headers(origin="http://testserver"),
        follow_redirects=False,
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


def test_ops_logout_rejects_cross_origin_post(monkeypatch) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 51082))
    response = client.post(
        "/ops/logout",
        data={"logout": "1"},
        headers={
            "X-Forwarded-For": "127.0.0.1",
            "Origin": "https://evil.example",
        },
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_ops_logout_get_is_not_allowed(monkeypatch) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())
    client = TestClient(app, client=("127.0.0.1", 5109))
    response = client.get(
        "/ops/logout",
        headers={"X-Forwarded-For": "127.0.0.1"},
        follow_redirects=False,
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


def test_ops_page_rejects_spoofed_forwarded_for_from_untrusted_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_ui,
        "get_settings",
        lambda: _settings(allowlist="10.0.0.0/8"),
    )

    client = TestClient(app, client=("198.51.100.10", 5102))
    response = client.get("/ops/referrals", headers={"X-Forwarded-For": "10.0.0.7"})

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}
