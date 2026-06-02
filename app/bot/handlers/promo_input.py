from __future__ import annotations

import re

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

PROMO_INPUT_RE = re.compile(r"^/?promo\s+(.+)$", re.IGNORECASE)


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
