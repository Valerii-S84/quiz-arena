from __future__ import annotations

from collections import deque
from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

import app.api.routes.ops_ui.security as security
from app.api.routes import ops_ui
from app.services.internal_auth import OPS_UI_SESSION_COOKIE
from app.services.ops_auth import OpsSessionStateError
from tests.type_helpers import build_request


def _settings(*, allowlist: str = "127.0.0.1/32") -> SimpleNamespace:
    return SimpleNamespace(
        internal_api_allowlist=allowlist,
        internal_api_trusted_proxies="127.0.0.1/32",
        redis_url="redis://unused-for-tests",
    )


def _form_request(
    *,
    host: str = "testserver",
    origin: str | None = "http://testserver",
    referer: str | None = None,
    content_type: str = "application/x-www-form-urlencoded",
    client_host: str = "127.0.0.1",
) -> Request:
    headers = {
        "host": host,
        "content-type": content_type,
        "x-forwarded-for": client_host,
    }
    if origin is not None:
        headers["origin"] = origin
    if referer is not None:
        headers["referer"] = referer
    return build_request(headers=headers, client_host=client_host)


@pytest.fixture(autouse=True)
def _clear_login_throttle() -> Generator[None, None, None]:
    ops_ui._LOGIN_FAILED_ATTEMPTS.clear()
    yield
    ops_ui._LOGIN_FAILED_ATTEMPTS.clear()


def test_assert_internal_ip_access_returns_allowed_client_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    client_ip = security._assert_internal_ip_access(
        build_request(headers={"x-forwarded-for": "127.0.0.1"})
    )

    assert client_ip == "127.0.0.1"


def test_assert_internal_ip_access_rejects_disallowed_client_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings(allowlist="10.0.0.0/8"))

    with pytest.raises(HTTPException) as exc_info:
        security._assert_internal_ip_access(build_request(headers={"x-forwarded-for": "127.0.0.1"}))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {"code": "E_FORBIDDEN"}


@pytest.mark.parametrize(
    ("origin", "referer"),
    [
        ("http://testserver/login", None),
        ("HTTPS://TESTSERVER/ops/login", None),
        (None, "http://testserver/ops/login"),
    ],
)
def test_assert_same_origin_form_post_accepts_same_origin_sources(
    origin: str | None,
    referer: str | None,
) -> None:
    security._assert_same_origin_form_post(
        _form_request(origin=origin, referer=referer),
        client_ip="127.0.0.1",
    )


@pytest.mark.parametrize(
    ("form_request", "expected_status"),
    [
        (_form_request(content_type="application/json"), 403),
        (_form_request(host="", origin="http://testserver"), 403),
        (_form_request(origin="https://evil.example"), 403),
        (_form_request(origin=None, referer="https://evil.example/path"), 403),
    ],
)
def test_assert_same_origin_form_post_rejects_invalid_form_posts(
    form_request: Request,
    expected_status: int,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        security._assert_same_origin_form_post(form_request, client_ip="127.0.0.1")

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == {"code": "E_FORBIDDEN"}


@pytest.mark.parametrize("value", ["http://[::1", "ftp://testserver", "http:///missing-host"])
def test_normalized_origin_rejects_malformed_or_unsupported_values(value: str) -> None:
    assert security._normalized_origin(value) is None


def test_login_rate_limit_returns_false_when_bucket_is_missing() -> None:
    assert security._is_login_rate_limited("127.0.0.1") is False


def test_login_rate_limit_records_prunes_and_clears_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 1000.0
    monkeypatch.setattr(ops_ui, "OPS_UI_LOGIN_MAX_FAILED_ATTEMPTS", 2)
    monkeypatch.setattr(ops_ui, "OPS_UI_LOGIN_FAILED_WINDOW_SECONDS", 10)
    monkeypatch.setattr(security, "monotonic", lambda: now)

    security._record_login_failure("127.0.0.1")
    security._record_login_failure("127.0.0.1")
    assert security._is_login_rate_limited("127.0.0.1") is True

    now = 1011.0
    assert security._is_login_rate_limited("127.0.0.1") is False
    assert "127.0.0.1" not in ops_ui._LOGIN_FAILED_ATTEMPTS

    ops_ui._LOGIN_FAILED_ATTEMPTS["unknown"] = deque([now])
    security._clear_login_failures(None)
    assert "unknown" not in ops_ui._LOGIN_FAILED_ATTEMPTS


@pytest.mark.asyncio
async def test_is_ops_ui_authenticated_validates_cookie_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    async def _validate_ops_ui_session(*, settings, session_id: str | None) -> bool:
        assert settings.redis_url == "redis://unused-for-tests"
        return session_id == "opaque-session"

    monkeypatch.setattr(security, "validate_ops_ui_session", _validate_ops_ui_session)

    authenticated = await security._is_ops_ui_authenticated(
        build_request(cookies={OPS_UI_SESSION_COOKIE: "opaque-session"}),
        client_ip="127.0.0.1",
    )

    assert authenticated is True


@pytest.mark.asyncio
async def test_is_ops_ui_authenticated_maps_unavailable_session_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ops_ui, "get_settings", lambda: _settings())

    async def _validate_ops_ui_session(*, settings, session_id: str | None) -> bool:
        del settings, session_id
        raise OpsSessionStateError("redis down")

    monkeypatch.setattr(security, "validate_ops_ui_session", _validate_ops_ui_session)

    with pytest.raises(HTTPException) as exc_info:
        await security._is_ops_ui_authenticated(
            build_request(cookies={OPS_UI_SESSION_COOKIE: "opaque-session"}),
            client_ip="127.0.0.1",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {"code": "E_AUTH_STATE_UNAVAILABLE"}
