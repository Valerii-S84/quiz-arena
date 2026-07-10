from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from app.workers.tasks import daily_cup_messaging_delivery as daily_delivery
from app.workers.tasks import tournaments_messaging_delivery as private_delivery

NOW_UTC = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


class _Bot:
    async def send_message(self, *, chat_id: int, **_kwargs):
        if chat_id == 20:
            raise RuntimeError("telegram failed")
        return SimpleNamespace(message_id=500 + chat_id)


class _Session:
    async def close(self) -> None:
        return None


class _WorkerBot(_Bot):
    session = _Session()


def _patch_delivery_tracking(monkeypatch, module):
    calls: dict[str, list[dict[str, object]]] = {"sent": [], "failed": []}

    async def _prepare(**kwargs):
        target = kwargs["target"]
        return SimpleNamespace(
            should_send=target.chat_id is not None,
            idempotency_key=target.idempotency_key,
        )

    async def _sent(**kwargs):
        calls["sent"].append(kwargs)

    async def _failed(**kwargs):
        calls["failed"].append(kwargs)

    monkeypatch.setattr(module, "prepare_telegram_delivery", _prepare)
    monkeypatch.setattr(module, "mark_telegram_delivery_sent", _sent)
    monkeypatch.setattr(module, "mark_telegram_delivery_failed", _failed)
    return calls


@pytest.mark.asyncio
async def test_daily_cup_round_delivery_records_sent_failed_and_skipped(monkeypatch) -> None:
    calls = _patch_delivery_tracking(monkeypatch, daily_delivery)
    tournament_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    tournament = SimpleNamespace(
        id=tournament_id,
        status="ROUND_1",
        current_round=1,
        round_deadline=NOW_UTC,
    )

    result = await daily_delivery.deliver_daily_cup_messages(
        bot=_Bot(),
        tournament=cast(Any, tournament),
        round_matches=[],
        standings_user_ids=[1, 2, 3],
        labels={1: "Ada", 2: "Bert", 3: "Cora"},
        telegram_targets={1: 10, 2: 20},
        points_by_user={1: "1", 2: "2", 3: "3"},
        tie_breaks_by_user={},
        place_by_user={1: 1, 2: 2, 3: 3},
        participant_rows=cast(
            Any,
            {
                1: SimpleNamespace(standings_message_id=None),
                2: SimpleNamespace(standings_message_id=None),
                3: SimpleNamespace(standings_message_id=None),
            },
        ),
        participants_total=3,
    )

    assert result["sent"] == 1
    assert result["failed"] == 1
    assert result["skipped"] == 1
    assert result["new_message_ids"] == {1: 510}
    assert len(calls["sent"]) == 1
    assert len(calls["failed"]) == 1


@pytest.mark.asyncio
async def test_private_tournament_delivery_records_sent_failed_and_skipped(monkeypatch) -> None:
    calls = _patch_delivery_tracking(monkeypatch, private_delivery)
    tournament_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    context = SimpleNamespace(
        parsed_tournament_id=tournament_id,
        standings_user_ids=[1, 2, 3],
        telegram_targets={1: 10, 2: 20},
        round_matches=[],
        labels={1: "Ada", 2: "Bert", 3: "Cora"},
        points_by_user={1: "1", 2: "2", 3: "3"},
        place_by_user={1: 1, 2: 2, 3: 3},
        participant_rows={
            1: SimpleNamespace(standings_message_id=None),
            2: SimpleNamespace(standings_message_id=None),
            3: SimpleNamespace(standings_message_id=None),
        },
        tournament=SimpleNamespace(
            id=tournament_id,
            status="ROUND_1",
            current_round=1,
            round_deadline=NOW_UTC,
            name="Liga",
            format="QUICK_5",
            invite_code="invite",
        ),
    )

    result = await private_delivery.deliver_round_messages(
        context=cast(Any, context),
        build_bot_fn=_WorkerBot,
        resolve_match_context_fn=lambda **_kwargs: (None, None),
        build_standings_lines_fn=lambda **_kwargs: ["A", "B"],
        build_completed_text_fn=lambda **_kwargs: "completed",
        build_round_text_fn=lambda **_kwargs: "round",
        format_deadline_fn=lambda _deadline: "deadline",
        build_keyboard_fn=lambda **_kwargs: "keyboard",
        add_share_button_fn=lambda **kwargs: kwargs["keyboard"],
        build_share_url_fn=lambda **_kwargs: "share",
        is_message_not_modified_error_fn=lambda _exc: False,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )

    assert result.sent == 1
    assert result.failed == 1
    assert result.skipped == 1
    assert result.new_message_ids == {1: 510}
    assert len(calls["sent"]) == 1
    assert len(calls["failed"]) == 1
