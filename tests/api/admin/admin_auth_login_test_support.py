from __future__ import annotations

from app.api.routes.admin import auth

ADMIN_AUTH = auth.admin_auth
ADMIN_RATE_LIMIT = auth.admin_rate_limit
AUTH_HELPERS = auth.auth_helpers


def login_buckets() -> AUTH_HELPERS.RateLimitBuckets:
    return AUTH_HELPERS.RateLimitBuckets(
        keys=("admin_login:ip:127.0.0.1", "admin_login:email:hash"),
        client_ip="127.0.0.1",
    )


def verify_buckets() -> AUTH_HELPERS.RateLimitBuckets:
    return AUTH_HELPERS.RateLimitBuckets(
        keys=("admin_2fa:ip:127.0.0.1", "admin_2fa:email:hash"),
        client_ip="127.0.0.1",
    )


__all__ = [
    "ADMIN_AUTH",
    "ADMIN_RATE_LIMIT",
    "AUTH_HELPERS",
    "login_buckets",
    "verify_buckets",
]
