from __future__ import annotations

import secrets

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_referral_code(length: int = 6) -> str:
    """Generates a short uppercase referral code with low typo ambiguity."""
    if length <= 0:
        raise ValueError("length must be positive")
    return "".join(secrets.choice(ALPHABET) for _ in range(length))
