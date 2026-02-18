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


def extract_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        candidate = forwarded_for.split(",", maxsplit=1)[0].strip()
        if candidate:
            return candidate

    if request.client is not None:
        return request.client.host

    return None


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
