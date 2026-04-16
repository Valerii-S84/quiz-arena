from __future__ import annotations

import pyotp

from app.core.config import Settings

from .auth_state import get_totp_secret, set_totp_secret


async def get_totp_setup_payload(*, settings: Settings) -> dict[str, str]:
    secret = await get_totp_secret(settings, strict=True)
    if not secret:
        secret = pyotp.random_base32()
        await set_totp_secret(settings=settings, secret=secret, strict=True)

    otpauth_uri = pyotp.TOTP(secret).provisioning_uri(
        name=settings.admin_email,
        issuer_name=settings.admin_totp_issuer,
    )
    return {
        "secret": secret,
        "otpauth_uri": otpauth_uri,
    }


async def verify_totp_code(*, settings: Settings, code: str) -> bool:
    secret = await get_totp_secret(settings, strict=True)
    if not secret:
        return False
    normalized = code.strip().replace(" ", "")
    if not normalized:
        return False
    totp = pyotp.TOTP(secret)
    return bool(totp.verify(normalized, valid_window=1))
