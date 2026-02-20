from __future__ import annotations

import ipaddress
import secrets
from functools import lru_cache

from fastapi import Request


def is_valid_internal_token(*, expected_token: str, received_token: str | None) -> bool:
    if not expected_token or not received_token:
        return False
    return secrets.compare_digest(expected_token, received_token)


@lru_cache(maxsize=32)
def _parse_allowlist(allowlist: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for raw_entry in allowlist.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue

        try:
            if "/" in entry:
                networks.append(ipaddress.ip_network(entry, strict=False))
            else:
                host = ipaddress.ip_address(entry)
                suffix = 32 if host.version == 4 else 128
                networks.append(ipaddress.ip_network(f"{entry}/{suffix}", strict=False))
        except ValueError:
            continue

    return tuple(networks)


def _parse_ip(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _is_trusted_proxy(*, proxy_ip: str | None, trusted_proxies: str) -> bool:
    return is_client_ip_allowed(client_ip=proxy_ip, allowlist=trusted_proxies)


def extract_client_ip(
    request: Request,
    *,
    trusted_proxies: str = "",
) -> str | None:
    client_host = _parse_ip(request.client.host if request.client is not None else None)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for and _is_trusted_proxy(proxy_ip=client_host, trusted_proxies=trusted_proxies):
        candidate = _parse_ip(forwarded_for.split(",", maxsplit=1)[0])
        if candidate is not None:
            return candidate
        return None

    return client_host


def is_client_ip_allowed(*, client_ip: str | None, allowlist: str) -> bool:
    if client_ip is None:
        return False

    try:
        parsed_ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    networks = _parse_allowlist(allowlist)
    if not networks:
        return False

    return any(parsed_ip in network for network in networks)
