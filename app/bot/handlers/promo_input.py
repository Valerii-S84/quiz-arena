from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from app.core.config import get_settings

PROMO_INPUT_RE = re.compile(r"^/?promo\s+(.+)$", re.IGNORECASE)
PROMO_WAIT_STARTED_AT_KEY = "promo_wait_started_at"


class PromoCode(StatesGroup):
    waiting_for_code = State()


def extract_promo_code(message: Message, *, allow_plain_text: bool = False) -> str | None:
    text = (message.text or "").strip()
    if not text:
        return None

    match = PROMO_INPUT_RE.match(text)
    if match is not None:
        promo_code = match.group(1).strip()
        return promo_code or None

    if allow_plain_text and not text.startswith("/"):
        return text

    return None


def resolve_attempt_source(message: Message, *, from_waiting_state: bool) -> str:
    text = (message.text or "").strip()
    if PROMO_INPUT_RE.match(text) is not None:
        return "COMMAND"
    if from_waiting_state:
        return "BUTTON"
    return "COMMAND"


async def mark_promo_waiting_started(state: FSMContext) -> None:
    await state.set_state(PromoCode.waiting_for_code)
    await state.update_data({PROMO_WAIT_STARTED_AT_KEY: _utc_timestamp()})


async def promo_waiting_is_expired(state: FSMContext) -> bool:
    started_at = _coerce_timestamp((await state.get_data()).get(PROMO_WAIT_STARTED_AT_KEY))
    if started_at is None:
        return True
    ttl_seconds = max(1, get_settings().promo_code_wait_ttl_seconds)
    return _utc_timestamp() - started_at > ttl_seconds


def _utc_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _coerce_timestamp(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None
