from __future__ import annotations

from types import SimpleNamespace

from app.bot.handlers.promo import _extract_promo_code
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
    assert _extract_promo_code(_message(text="/promo CHIK")) == "CHIK"


def test_extract_promo_code_does_not_parse_plain_text_anymore() -> None:
    assert _extract_promo_code(_message(text="CHIK")) is None


def test_extract_promo_code_from_reply_prompt() -> None:
    assert _extract_promo_code(_message(text="CHIK", reply_to_promo_prompt=True)) == "CHIK"


def test_extract_promo_code_ignores_other_commands_in_reply_flow() -> None:
    assert _extract_promo_code(_message(text="/start", reply_to_promo_prompt=True)) is None
