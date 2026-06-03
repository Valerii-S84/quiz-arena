from __future__ import annotations

import secrets

PROMO_OPEN_CALLBACK_PREFIX = "promo:open:"


def generate_promo_menu_nonce() -> str:
    return secrets.token_urlsafe(9)


def build_promo_open_callback_data(nonce: str) -> str:
    return f"{PROMO_OPEN_CALLBACK_PREFIX}{nonce}"


def extract_promo_open_nonce(callback_data: str | None) -> str | None:
    if callback_data is None or not callback_data.startswith(PROMO_OPEN_CALLBACK_PREFIX):
        return None
    nonce = callback_data.removeprefix(PROMO_OPEN_CALLBACK_PREFIX)
    return nonce or None
