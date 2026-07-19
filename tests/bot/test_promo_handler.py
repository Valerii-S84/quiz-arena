from __future__ import annotations

from types import SimpleNamespace

from app.bot.handlers.promo_input import extract_promo_code
from app.bot.texts.de import TEXTS_DE


def _message(*, text: str, reply_to_promo_prompt: bool = False):
    reply_to_message = None
    if reply_to_promo_prompt:
        reply_to_message = SimpleNamespace(
            from_user=SimpleNamespace(is_bot=True),
            text=f"{TEXTS_DE['msg.promo.reply_prefix']} prompt",
        )
    return SimpleNamespace(text=text, reply_to_message=reply_to_message)


def test_extract_promo_code_from_slash_command() -> None:
    assert extract_promo_code(_message(text="/promo CHIK")) == "CHIK"


def test_extract_promo_code_ignores_standalone_plain_text_code() -> None:
    assert extract_promo_code(_message(text="CHIK")) is None


def test_extract_promo_code_accepts_plain_text_when_waiting_for_code() -> None:
    assert extract_promo_code(_message(text="CHIK"), allow_plain_text=True) == "CHIK"


def test_extract_promo_code_ignores_plain_text_non_code() -> None:
    assert extract_promo_code(_message(text="hello world")) is None


def test_extract_promo_code_ignores_stale_reply_prompt_outside_waiting_state() -> None:
    assert extract_promo_code(_message(text="CHIK", reply_to_promo_prompt=True)) is None


def test_extract_promo_code_ignores_other_commands_in_waiting_state() -> None:
    assert extract_promo_code(_message(text="/start"), allow_plain_text=True) is None
