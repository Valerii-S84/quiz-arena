from __future__ import annotations

import hashlib
import hmac
import re

_PROMO_NORMALIZE_PATTERN = re.compile(r"[\s-]+")


def normalize_promo_code(raw_code: str) -> str:
    normalized = raw_code.strip().upper()
    return _PROMO_NORMALIZE_PATTERN.sub("", normalized)


def hash_promo_code(*, normalized_code: str, pepper: str) -> str:
    digest = hmac.new(
        pepper.encode("utf-8"),
        normalized_code.encode("utf-8"),
        hashlib.sha256,
    )
    return digest.hexdigest()
