from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.workers.tasks import daily_cup_messaging_delivery, tournaments_messaging_delivery
from app.workers.tasks.tournaments_messaging_context import TournamentRoundMessagingContext
from tests.game.tournaments_unit_support import NOW_UTC, match_row, participant_row, tournament_row


def _patch_delivery_tracking(monkeypatch: pytest.MonkeyPatch, module) -> None:
    async def _prepare(**kwargs):
        target = kwargs["target"]
        return SimpleNamespace(
            should_send=target.chat_id is not None,
            idempotency_key=target.idempotency_key,
        )

    async def _mark_terminal(**_kwargs) -> None:
        return None

    monkeypatch.setattr(module, "prepare_telegram_delivery", _prepare)
    monkeypatch.setattr(module, "mark_telegram_delivery_sent", _mark_terminal)
    monkeypatch.setattr(module, "mark_telegram_delivery_failed", _mark_terminal)
    monkeypatch.setattr(module, "record_telegram_delivery_skipped", _mark_terminal)


@pytest.mark.asyncio
async def test_deliver_round_messages_sends_edits_replaces_and_counts_missing_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_delivery_tracking(monkeypatch, tournaments_messaging_delivery)
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

    result = await tournaments_messaging_delivery.deliver_round_messages(
        context=context,
        build_bot_fn=lambda: bot,
        resolve_match_context_fn=lambda **_kwargs: (None, None),
        build_standings_lines_fn=lambda **_kwargs: ["standings"],
        build_completed_text_fn=lambda **_kwargs: "completed",
        build_round_text_fn=lambda **_kwargs: "round",
        format_deadline_fn=lambda _deadline: "deadline",
        build_keyboard_fn=lambda **_kwargs: "keyboard",
        add_share_button_fn=lambda **_kwargs: "share-keyboard",
        build_share_url_fn=lambda **_kwargs: "https://example.test",
        is_message_not_modified_error_fn=lambda _exc: False,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )

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
    _patch_delivery_tracking(monkeypatch, tournaments_messaging_delivery)
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

    result = await tournaments_messaging_delivery.deliver_round_messages(
        context=context,
        build_bot_fn=lambda: bot,
        resolve_match_context_fn=lambda **_kwargs: (None, 22),
        build_standings_lines_fn=lambda **_kwargs: ["standings"],
        build_completed_text_fn=lambda **_kwargs: "completed",
        build_round_text_fn=lambda **_kwargs: "round",
        format_deadline_fn=lambda _deadline: "deadline",
        build_keyboard_fn=lambda **_kwargs: "keyboard",
        add_share_button_fn=lambda **_kwargs: "share-keyboard",
        build_share_url_fn=lambda **_kwargs: "https://example.test",
        is_message_not_modified_error_fn=lambda _exc: True,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )

    assert result.sent == 0
    assert result.edited == 1
    assert result.failed == 0


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
    _patch_delivery_tracking(monkeypatch, daily_cup_messaging_delivery)

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
    assert result["failed"] == 0
    assert result["skipped"] == 1
    assert result["new_message_ids"] == {11: 901}
    assert result["replaced_message_ids"] == {22: 902}


class _Bot:
    def __init__(self, *, edit_outcomes: list[object]) -> None:
        self._message_id = 900
        self._edit_outcomes = edit_outcomes
        self.closed = False
        self.session = SimpleNamespace(close=self._close)

    async def send_message(self, **_kwargs):
        self._message_id += 1
        return SimpleNamespace(message_id=self._message_id)

    async def edit_message_text(self, **_kwargs) -> None:
        outcome = self._edit_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

    async def _close(self) -> None:
        self.closed = True
