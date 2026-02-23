from __future__ import annotations

from types import SimpleNamespace

from app.services.internal_auth import (
    OPS_UI_SESSION_COOKIE,
    build_ops_ui_session_value,
    extract_client_ip,
    is_client_ip_allowed,
    is_internal_request_authenticated,
    is_valid_internal_token,
    is_valid_ops_ui_session,
)


def test_is_valid_internal_token_requires_exact_match() -> None:
    assert is_valid_internal_token(expected_token="secret", received_token="secret") is True
    assert is_valid_internal_token(expected_token="secret", received_token="wrong") is False
    assert is_valid_internal_token(expected_token="secret", received_token=None) is False


def test_is_valid_ops_ui_session_requires_matching_hashed_value() -> None:
    session_value = build_ops_ui_session_value(token="secret")
    assert is_valid_ops_ui_session(expected_token="secret", received_session=session_value) is True
    assert is_valid_ops_ui_session(expected_token="secret", received_session="wrong") is False
    assert is_valid_ops_ui_session(expected_token="secret", received_session=None) is False


def test_is_internal_request_authenticated_accepts_token_or_ops_session() -> None:
    request_with_token = SimpleNamespace(headers={"X-Internal-Token": "secret"}, cookies={})
    assert is_internal_request_authenticated(request_with_token, expected_token="secret") is True

    request_with_session = SimpleNamespace(
        headers={},
        cookies={OPS_UI_SESSION_COOKIE: build_ops_ui_session_value(token="secret")},
    )
    assert is_internal_request_authenticated(request_with_session, expected_token="secret") is True

    request_without_credentials = SimpleNamespace(headers={}, cookies={})
    assert (
        is_internal_request_authenticated(request_without_credentials, expected_token="secret")
        is False
    )


def test_is_client_ip_allowed_supports_exact_ip_and_cidr() -> None:
    allowlist = "127.0.0.1,10.0.0.0/8"
    assert is_client_ip_allowed(client_ip="127.0.0.1", allowlist=allowlist) is True
    assert is_client_ip_allowed(client_ip="10.12.33.1", allowlist=allowlist) is True
    assert is_client_ip_allowed(client_ip="192.168.1.5", allowlist=allowlist) is False


def test_extract_client_ip_uses_forwarded_header_only_for_trusted_proxy() -> None:
    request = SimpleNamespace(
        headers={"X-Forwarded-For": "10.1.1.8, 127.0.0.1"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert extract_client_ip(request, trusted_proxies="127.0.0.1/32") == "10.1.1.8"


def test_extract_client_ip_ignores_forwarded_header_for_untrusted_proxy() -> None:
    request = SimpleNamespace(
        headers={"X-Forwarded-For": "10.1.1.8, 127.0.0.1"},
        client=SimpleNamespace(host="198.51.100.10"),
    )
    assert extract_client_ip(request, trusted_proxies="127.0.0.1/32") == "198.51.100.10"


def test_extract_client_ip_rejects_invalid_forwarded_header_for_trusted_proxy() -> None:
    request = SimpleNamespace(
        headers={"X-Forwarded-For": "not-an-ip, 127.0.0.1"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert extract_client_ip(request, trusted_proxies="127.0.0.1/32") is None


def test_extract_client_ip_supports_ipv6_forwarded_header() -> None:
    request = SimpleNamespace(
        headers={"X-Forwarded-For": "2001:db8::10, 127.0.0.1"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert extract_client_ip(request, trusted_proxies="127.0.0.1/32") == "2001:db8::10"


def test_extract_client_ip_falls_back_to_client_host() -> None:
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
    assert extract_client_ip(request) == "127.0.0.1"
