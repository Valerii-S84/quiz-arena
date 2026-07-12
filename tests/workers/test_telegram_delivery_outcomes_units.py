from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from app.workers.tasks import daily_cup_message_delivery_persistence as daily_persistence
from app.workers.tasks import daily_cup_messaging_delivery as daily_delivery
from app.workers.tasks import tournaments_messaging_delivery as private_delivery

NOW_UTC = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


class _Bot:
    def __init__(self) -> None:
        self.edits: list[dict[str, object]] = []
        self.sent_messages: list[dict[str, object]] = []

    async def send_message(self, *, chat_id: int, **_kwargs):
        self.sent_messages.append({"chat_id": chat_id, **_kwargs})
        if chat_id == 20:
            raise RuntimeError("telegram failed")
        return SimpleNamespace(message_id=500 + chat_id)

    async def edit_message_text(self, **kwargs) -> None:
        self.edits.append(kwargs)


class _Session:
    async def close(self) -> None:
        return None


class _WorkerBot(_Bot):
    session = _Session()


@pytest.mark.asyncio
async def test_daily_cup_message_id_persists_before_sent(monkeypatch) -> None:
    calls: list[str] = []

    async def _persist(**_kwargs) -> None:
        calls.append("persist")

    async def _sent(**_kwargs) -> None:
        calls.append("sent")

    monkeypatch.setattr(daily_persistence, "persist_daily_cup_standings_message_ids", _persist)
    monkeypatch.setattr(daily_persistence, "mark_telegram_delivery_sent", _sent)

    result = await daily_persistence.persist_daily_cup_sent_message(
        cast(Any, SimpleNamespace(idempotency_key="delivery-key")),
        UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        1,
        SimpleNamespace(message_id=501),
        NOW_UTC,
    )

    assert result == 501
    assert calls == ["persist", "sent"]


@pytest.mark.asyncio
async def test_daily_cup_persistence_failure_does_not_mark_sent(monkeypatch) -> None:
    sent_calls: list[object] = []

    async def _persist(**_kwargs) -> None:
        raise RuntimeError("db unavailable")

    async def _sent(**_kwargs) -> None:
        sent_calls.append(object())

    monkeypatch.setattr(daily_persistence, "persist_daily_cup_standings_message_ids", _persist)
    monkeypatch.setattr(daily_persistence, "mark_telegram_delivery_sent", _sent)

    with pytest.raises(RuntimeError, match="db unavailable"):
        await daily_persistence.persist_daily_cup_sent_message(
            cast(Any, SimpleNamespace(idempotency_key="delivery-key")),
            UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            1,
            SimpleNamespace(message_id=501),
            NOW_UTC,
        )

    assert sent_calls == []


def _patch_delivery_tracking(monkeypatch, module):
    calls: dict[str, list[dict[str, object]]] = dict(sent=[], failed=[], dispatch=[], persisted=[])

    async def _prepare(**kwargs):
        target = kwargs["target"]
        return SimpleNamespace(
            should_send=target.chat_id is not None,
            idempotency_key=target.idempotency_key,
        )

    async def _sent(**kwargs):
        calls["sent"].append(kwargs)

    async def _dispatch(delivery, **_kwargs):
        calls["dispatch"].append({"idempotency_key": delivery.idempotency_key})

    async def _persist_sent(target, *_args, **_kwargs) -> int:
        calls["persisted"].append({"idempotency_key": target.idempotency_key})
        calls["sent"].append({"idempotency_key": target.idempotency_key})
        return int(_args[2].message_id)

    async def _failed(**kwargs):
        calls["failed"].append(kwargs)

    monkeypatch.setattr(module, "prepare_telegram_delivery", _prepare)
    monkeypatch.setattr(module, "begin_telegram_delivery_dispatch", _dispatch)
    monkeypatch.setattr(module, "mark_telegram_delivery_sent", _sent)
    if hasattr(module, "persist_daily_cup_sent_message"):
        monkeypatch.setattr(module, "persist_daily_cup_sent_message", _persist_sent)
    monkeypatch.setattr(
        module, "persist_private_tournament_sent_message", _persist_sent, raising=False
    )
    monkeypatch.setattr(module, "mark_telegram_delivery_failed", _failed)
    monkeypatch.setattr(module, "record_telegram_delivery_skipped", _sent, raising=False)
    _patch_fallback_terminal_helpers(monkeypatch, module, _sent, _failed)
    return calls


def _patch_idempotent_prepare(monkeypatch, module):
    seen: set[str] = set()
    prepared: list[str] = []

    async def _prepare(**kwargs):
        target = kwargs["target"]
        prepared.append(target.idempotency_key)
        should_send = target.chat_id is not None and target.idempotency_key not in seen
        if should_send:
            seen.add(target.idempotency_key)
        return SimpleNamespace(
            should_send=should_send,
            idempotency_key=target.idempotency_key,
        )

    async def _mark_terminal(**_kwargs) -> None:
        return None

    async def _persist_sent(_target, *_args, **_kwargs) -> int:
        return int(_args[2].message_id)

    monkeypatch.setattr(module, "prepare_telegram_delivery", _prepare)
    monkeypatch.setattr(module, "mark_telegram_delivery_sent", _mark_terminal)
    if hasattr(module, "persist_daily_cup_sent_message"):
        monkeypatch.setattr(module, "persist_daily_cup_sent_message", _persist_sent)
    monkeypatch.setattr(
        module, "persist_private_tournament_sent_message", _persist_sent, raising=False
    )
    monkeypatch.setattr(module, "mark_telegram_delivery_failed", _mark_terminal)
    monkeypatch.setattr(
        module,
        "record_telegram_delivery_skipped",
        _mark_terminal,
        raising=False,
    )
    _patch_fallback_terminal_helpers(monkeypatch, module, _mark_terminal, _mark_terminal)
    return prepared


def _patch_fallback_terminal_helpers(monkeypatch, module, skipped_handler, failed_handler) -> None:
    if hasattr(module, "fallback_delivery"):
        monkeypatch.setattr(
            module.fallback_delivery,
            "record_original_edit_skipped_after_fallback_success",
            skipped_handler,
        )
        monkeypatch.setattr(
            module.fallback_delivery,
            "record_original_edit_skipped_after_fallback_skip",
            skipped_handler,
        )
        monkeypatch.setattr(
            module.fallback_delivery,
            "mark_original_edit_failed_after_fallback_failure",
            failed_handler,
        )
        return
    monkeypatch.setattr(
        module,
        "record_original_edit_skipped_after_fallback_success",
        skipped_handler,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "record_original_edit_skipped_after_fallback_skip",
        skipped_handler,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "mark_original_edit_failed_after_fallback_failure",
        failed_handler,
        raising=False,
    )


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
    assert len(calls["dispatch"]) == 2
    assert len(calls["persisted"]) == 1
    assert len(calls["sent"]) == 1
    assert len(calls["failed"]) == 1


@pytest.mark.asyncio
async def test_daily_cup_round_delivery_versions_same_message_id_by_round(monkeypatch) -> None:
    prepared = _patch_idempotent_prepare(monkeypatch, daily_delivery)
    bot = _Bot()
    tournament_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    participant_rows = {1: SimpleNamespace(standings_message_id=222)}

    async def _deliver(*, status: str, current_round: int):
        return await daily_delivery.deliver_daily_cup_messages(
            bot=bot,
            tournament=cast(
                Any,
                SimpleNamespace(
                    id=tournament_id,
                    status=status,
                    current_round=current_round,
                    round_deadline=NOW_UTC,
                ),
            ),
            round_matches=[],
            standings_user_ids=[1],
            labels={1: "Ada"},
            telegram_targets={1: 10},
            points_by_user={1: "1"},
            tie_breaks_by_user={1: "1"},
            place_by_user={1: 1},
            participant_rows=cast(Any, participant_rows),
            participants_total=2,
        )

    round_1 = await _deliver(status="ROUND_1", current_round=1)
    round_2 = await _deliver(status="ROUND_2", current_round=2)
    duplicate_round_2 = await _deliver(status="ROUND_2", current_round=2)
    final = await _deliver(status="COMPLETED", current_round=2)

    assert round_1["edited"] == 1
    assert round_2["edited"] == 1
    assert duplicate_round_2["skipped"] == 1
    assert final["edited"] == 1
    assert len(bot.edits) == 3
    assert len(set(prepared)) == 3
    assert any("round:1:status:round_1" in key for key in prepared)
    assert any("round:2:status:round_2" in key for key in prepared)
    assert any("status:completed" in key for key in prepared)


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


@pytest.mark.asyncio
async def test_private_tournament_round_delivery_versions_and_keeps_users_separate(
    monkeypatch,
) -> None:
    prepared = _patch_idempotent_prepare(monkeypatch, private_delivery)
    bot = _WorkerBot()
    tournament_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    async def _deliver(*, user_ids: list[int], current_round: int):
        context = SimpleNamespace(
            parsed_tournament_id=tournament_id,
            standings_user_ids=user_ids,
            telegram_targets={1: 10, 2: 20},
            round_matches=[],
            labels={1: "Ada", 2: "Bert"},
            points_by_user={1: "1", 2: "2"},
            place_by_user={1: 1, 2: 2},
            participant_rows={
                user_id: SimpleNamespace(standings_message_id=222) for user_id in user_ids
            },
            tournament=SimpleNamespace(
                id=tournament_id,
                status=f"ROUND_{current_round}",
                current_round=current_round,
                round_deadline=NOW_UTC,
                name="Liga",
                format="QUICK_5",
                invite_code="invite",
            ),
        )
        return await private_delivery.deliver_round_messages(
            context=cast(Any, context),
            build_bot_fn=lambda: bot,
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

    round_1 = await _deliver(user_ids=[1], current_round=1)
    round_2 = await _deliver(user_ids=[1], current_round=2)
    duplicate_user_1_plus_user_2 = await _deliver(user_ids=[1, 2], current_round=2)

    assert round_1.edited == 1
    assert round_2.edited == 1
    assert duplicate_user_1_plus_user_2.edited == 1
    assert duplicate_user_1_plus_user_2.skipped == 1
    assert len(bot.edits) == 3
    assert len(set(prepared)) == 3
    assert any("1:phase:round:2:status:round_2" in key for key in prepared)
    assert any("2:phase:round:2:status:round_2" in key for key in prepared)
