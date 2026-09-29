from types import SimpleNamespace

import pytest

from app.bot.handlers.channel_bonus_compat import handle_legacy_channel_bonus_callback
from tests.bot.helpers import DummyCallback


@pytest.mark.parametrize(
    "callback_data",
    [
        "channel_bonus:open",
        "channel_bonus:check",
        "channel_bonus:claimed",
        "channel_bonus:channel_unavailable",
    ],
)
async def test_legacy_channel_bonus_callback_is_acknowledged(callback_data: str) -> None:
    callback = DummyCallback(
        data=callback_data,
        from_user=SimpleNamespace(id=17),
    )

    await handle_legacy_channel_bonus_callback(callback)

    assert callback.answer_calls == [
        {
            "text": "Dieser Bonus ist nicht mehr verfügbar.",
            "show_alert": True,
        }
    ]
