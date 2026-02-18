from __future__ import annotations

from types import SimpleNamespace

from app.services.internal_auth import (
    extract_client_ip,
    is_client_ip_allowed,
    is_valid_internal_token,
)


def test_is_valid_internal_token_requires_exact_match() -> None:
    assert is_valid_internal_token(expected_token="secret", received_token="secret") is True
    assert is_valid_internal_token(expected_token="secret", received_token="wrong") is False
    assert is_valid_internal_token(expected_token="secret", received_token=None) is False


def test_is_client_ip_allowed_supports_exact_ip_and_cidr() -> None:
    allowlist = "127.0.0.1,10.0.0.0/8"
    assert is_client_ip_allowed(client_ip="127.0.0.1", allowlist=allowlist) is True
    assert is_client_ip_allowed(client_ip="10.12.33.1", allowlist=allowlist) is True
    assert is_client_ip_allowed(client_ip="192.168.1.5", allowlist=allowlist) is False


def test_extract_client_ip_prefers_forwarded_header() -> None:
    request = SimpleNamespace(
        headers={"X-Forwarded-For": "10.1.1.8, 127.0.0.1"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert extract_client_ip(request) == "10.1.1.8"


def test_extract_client_ip_falls_back_to_client_host() -> None:
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
    assert extract_client_ip(request) == "127.0.0.1"
