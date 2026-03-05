from __future__ import annotations

from app.core.config import get_settings

_DEFAULT_PUBLIC_BOT_USERNAME = "Deine_Deutsch_Quiz_bot"


def public_bot_username() -> str:
    configured = get_settings().telegram_public_bot_username.strip()
    return configured or _DEFAULT_PUBLIC_BOT_USERNAME


def public_bot_link() -> str:
    return f"https://t.me/{public_bot_username()}"


def public_bot_start_link(*, start_param: str) -> str:
    return f"{public_bot_link()}?start={start_param}"
