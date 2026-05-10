from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from aiogram.types import BufferedInputFile

from app.workers.tasks.daily_cup_proof_card_sender import send_daily_cup_proof_card


class _PhotoBot:
    def __init__(self, message_photo: list[object] | None) -> None:
        self.calls: list[dict[str, object]] = []
        self._message_photo = message_photo

    async def send_photo(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(photo=self._message_photo)


def _record_render(target: list[dict[str, object]]):
    def _inner(**kwargs) -> bytes:
        target.append(kwargs)
        return b"png"

    return _inner


def test_send_daily_cup_proof_card_reuses_cached_file_id() -> None:
    bot = _PhotoBot(message_photo=[])
    rendered: list[dict[str, object]] = []

    result = asyncio.run(
        send_daily_cup_proof_card(
            bot=bot,
            tournament_id="tid",
            user_id=5,
            chat_id=50,
            place=1,
            points="7",
            participants_total=8,
            cached_file_id="cached-file",
            player_label="Ada",
            now_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            rounds_played=3,
            render_card_png=_record_render(rendered),
        )
    )

    assert result == (True, True, None)
    assert bot.calls[0]["photo"] == "cached-file"
    assert rendered == []


def test_send_daily_cup_proof_card_renders_upload_and_returns_file_id() -> None:
    bot = _PhotoBot(message_photo=[SimpleNamespace(file_id="new-file")])
    rendered: list[dict[str, object]] = []

    result = asyncio.run(
        send_daily_cup_proof_card(
            bot=bot,
            tournament_id="tid",
            user_id=5,
            chat_id=50,
            place=2,
            points="6.5",
            participants_total=8,
            cached_file_id=None,
            player_label="Ada",
            now_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            rounds_played=4,
            render_card_png=_record_render(rendered),
        )
    )

    assert result == (True, False, "new-file")
    assert isinstance(bot.calls[0]["photo"], BufferedInputFile)
    assert rendered[0]["player_label"] == "Ada"
    assert rendered[0]["is_daily_arena"] is True
