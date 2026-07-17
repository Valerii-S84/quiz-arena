from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.workers.tasks import daily_cup_messaging_delivery, tournaments_messaging_delivery
from app.workers.tasks.tournaments_messaging_context import TournamentRoundMessagingContext
from tests.game.tournaments_unit_support import NOW_UTC, match_row, participant_row, tournament_row


@pytest.mark.asyncio
async def test_deliver_round_messages_sends_edits_replaces_and_counts_missing_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_tournament_delivery_persistence(monkeypatch)
    tournament = tournament_row(status="COMPLETED")
    context = TournamentRoundMessagingContext(
        parsed_tournament_id=tournament.id,
        tournament=tournament,
        standings_user_ids=[11, 22, 33, 44],
        points_by_user={11: "2", 22: "1", 33: "0", 44: "0"},
        place_by_user={11: 1, 22: 2, 33: 3, 44: 4},
        participant_rows={
            11: SimpleNamespace(standings_message_id=None),
            22: SimpleNamespace(standings_message_id=222),
            33: SimpleNamespace(standings_message_id=333),
            44: SimpleNamespace(standings_message_id=444),
        },
        telegram_targets={11: 101, 22: 102, 33: 103},
        labels={11: "A", 22: "B", 33: "C", 44: "D"},
        round_matches=[],
    )
    bot = _Bot(edit_outcomes=[None, RuntimeError("replace")])

    result = await _deliver_private_round(context=context, bot=bot)

    assert result.sent == 2
    assert result.edited == 1
    assert result.failed == 0
    assert result.skipped == 1
    assert result.new_message_ids == {11: 901}
    assert result.replaced_message_ids == {33: 902}
    assert bot.closed


@pytest.mark.asyncio
async def test_deliver_round_messages_counts_not_modified_as_edited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_tournament_delivery_persistence(monkeypatch)
    tournament = tournament_row(status="ROUND_1", current_round=1, round_deadline=NOW_UTC)
    context = TournamentRoundMessagingContext(
        parsed_tournament_id=tournament.id,
        tournament=tournament,
        standings_user_ids=[11],
        points_by_user={11: "2"},
        place_by_user={11: 1},
        participant_rows={11: SimpleNamespace(standings_message_id=222)},
        telegram_targets={11: 101},
        labels={11: "A"},
        round_matches=[],
    )
    bot = _Bot(edit_outcomes=[RuntimeError("not modified")])

    result = await _deliver_private_round(context=context, bot=bot, not_modified=True)

    assert result.sent == 0
    assert result.edited == 1
    assert result.failed == 0
    assert result.skipped == 0


@pytest.mark.asyncio
async def test_deliver_round_messages_surfaces_initial_retryable_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_tournament_delivery_persistence(
        monkeypatch,
        failure_result=SimpleNamespace(
            status="RETRY",
            retry_after_seconds=7,
        ),
    )
    tournament = tournament_row(status="ROUND_1", current_round=1, round_deadline=NOW_UTC)
    context = TournamentRoundMessagingContext(
        parsed_tournament_id=tournament.id,
        tournament=tournament,
        standings_user_ids=[11],
        points_by_user={11: "2"},
        place_by_user={11: 1},
        participant_rows={11: SimpleNamespace(standings_message_id=None)},
        telegram_targets={11: 101},
        labels={11: "A"},
        round_matches=[],
    )
    bot = _Bot(
        edit_outcomes=[],
        send_outcomes=[RuntimeError("flood")],
    )

    result = await _deliver_private_round(context=context, bot=bot)

    assert result.sent == 0
    assert result.failed == 1
    assert result.skipped == 0
    assert result.retry_count == 1
    assert result.retry_after_seconds == 7
    assert bot.closed


@pytest.mark.asyncio
async def test_fallback_retry_does_not_terminalize_original_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure_calls: list[object] = []
    _patch_tournament_delivery_persistence(
        monkeypatch,
        failure_result=SimpleNamespace(status="RETRY", retry_after_seconds=7),
        failure_calls=failure_calls,
    )
    tournament = tournament_row(status="ROUND_1", current_round=1, round_deadline=NOW_UTC)
    context = TournamentRoundMessagingContext(
        parsed_tournament_id=tournament.id,
        tournament=tournament,
        standings_user_ids=[11],
        points_by_user={11: "2"},
        place_by_user={11: 1},
        participant_rows={11: SimpleNamespace(standings_message_id=222)},
        telegram_targets={11: 101},
        labels={11: "A"},
        round_matches=[],
    )
    bot = _Bot(
        edit_outcomes=[RuntimeError("edit unavailable")],
        send_outcomes=[RuntimeError("flood")],
    )

    result = await _deliver_private_round(context=context, bot=bot)

    assert result.retry_count == 1
    assert result.retry_after_seconds == 7
    assert len(failure_calls) == 1


@pytest.mark.asyncio
async def test_deliver_daily_cup_messages_handles_send_edit_and_missing_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = tournament_row(type="DAILY_ARENA", status="COMPLETED")
    participant_rows = {
        11: participant_row(tournament_id=tournament.id, user_id=11),
        22: participant_row(tournament_id=tournament.id, user_id=22),
        33: participant_row(tournament_id=tournament.id, user_id=33),
    }
    participant_rows[22].standings_message_id = 222
    bot = _Bot(edit_outcomes=[RuntimeError("replace")])

    monkeypatch.setattr(
        daily_cup_messaging_delivery,
        "build_daily_cup_lobby_keyboard",
        lambda **_kwargs: "keyboard",
    )
    monkeypatch.setattr(
        daily_cup_messaging_delivery, "build_daily_cup_share_url", lambda **_kwargs: "url"
    )
    monkeypatch.setattr(daily_cup_messaging_delivery, "public_bot_link", lambda: "bot-link")
    monkeypatch.setattr(
        daily_cup_messaging_delivery, "is_message_not_modified_error", lambda _exc: False
    )

    result = await daily_cup_messaging_delivery.deliver_daily_cup_messages(
        bot=bot,
        tournament=tournament,
        round_matches=[match_row(tournament_id=tournament.id, challenge_id=uuid4())],
        standings_user_ids=[11, 22, 33],
        labels={11: "A", 22: "B", 33: "C"},
        telegram_targets={11: 101, 22: 102},
        points_by_user={11: "2", 22: "1", 33: "0"},
        tie_breaks_by_user={11: "5", 22: "3", 33: "1"},
        place_by_user={11: 1, 22: 2, 33: 3},
        participant_rows=participant_rows,
        participants_total=3,
    )

    assert result["sent"] == 2
    assert result["edited"] == 0
    assert result["failed"] == 1
    assert result["new_message_ids"] == {11: 901}
    assert result["replaced_message_ids"] == {22: 902}


def _patch_tournament_delivery_persistence(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failure_result: object = SimpleNamespace(status="FAILED"),
    failure_calls: list[object] | None = None,
) -> None:
    async def _prepare_delivery(target):
        return SimpleNamespace(should_send=target.chat_id is not None)

    async def _record_delivery_failure(_target, _exc):
        if failure_calls is not None:
            failure_calls.append(_target)
        return failure_result

    async def _record_delivery_skipped(*_args, **_kwargs):
        return None

    async def _persist_sent_message(_target, _fence, message, _happened_at, **_kwargs):
        return int(message if isinstance(message, int) else message.message_id)

    monkeypatch.setattr(
        tournaments_messaging_delivery,
        "prepare_private_tournament_delivery",
        _prepare_delivery,
    )
    monkeypatch.setattr(
        tournaments_messaging_delivery,
        "record_private_tournament_delivery_failure",
        _record_delivery_failure,
    )
    monkeypatch.setattr(
        tournaments_messaging_delivery,
        "record_private_tournament_delivery_skipped",
        _record_delivery_skipped,
    )
    monkeypatch.setattr(
        tournaments_messaging_delivery,
        "persist_private_tournament_sent_message",
        _persist_sent_message,
    )


async def _deliver_private_round(
    *,
    context: TournamentRoundMessagingContext,
    bot: object,
    not_modified: bool = False,
):
    return await tournaments_messaging_delivery.deliver_round_messages(
        context=context,
        build_bot_fn=lambda: bot,
        resolve_match_context_fn=lambda **_kwargs: (None, 22 if not_modified else None),
        build_standings_lines_fn=lambda **_kwargs: ["standings"],
        build_completed_text_fn=lambda **_kwargs: "completed",
        build_round_text_fn=lambda **_kwargs: "round",
        format_deadline_fn=lambda _deadline: "deadline",
        build_keyboard_fn=lambda **_kwargs: "keyboard",
        add_share_button_fn=lambda **_kwargs: "share-keyboard",
        build_share_url_fn=lambda **_kwargs: "https://example.test",
        is_message_not_modified_error_fn=lambda _exc: not_modified,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )


class _Bot:
    def __init__(
        self,
        *,
        edit_outcomes: list[object],
        send_outcomes: list[object] | None = None,
    ) -> None:
        self._message_id = 900
        self._edit_outcomes = edit_outcomes
        self._send_outcomes = list(send_outcomes or [])
        self.closed = False
        self.session = SimpleNamespace(close=self._close)

    async def send_message(self, **_kwargs):
        if self._send_outcomes:
            outcome = self._send_outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            if isinstance(outcome, int):
                return SimpleNamespace(message_id=outcome)
        self._message_id += 1
        return SimpleNamespace(message_id=self._message_id)

    async def edit_message_text(self, **_kwargs) -> None:
        outcome = self._edit_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

    async def _close(self) -> None:
        self.closed = True
