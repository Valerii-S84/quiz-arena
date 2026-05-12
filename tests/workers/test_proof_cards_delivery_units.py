from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.workers.tasks import tournaments_proof_cards_delivery as delivery
from app.workers.tasks import tournaments_proof_cards_sender as sender
from tests.game.tournaments_unit_support import NOW_UTC, participant_row, tournament_row
from tests.workers.payments_reliability_async_support import SessionLocalStub


@pytest.mark.asyncio
async def test_load_proof_card_context_filters_invalid_and_user_specific() -> None:
    tournament = tournament_row(status="COMPLETED")
    participants = [
        participant_row(tournament_id=tournament.id, user_id=11, score="2"),
        participant_row(tournament_id=tournament.id, user_id=22, score="1"),
    ]
    users = [
        SimpleNamespace(id=11, telegram_user_id=101, username="a", first_name=None),
        SimpleNamespace(id=22, telegram_user_id=102, username=None, first_name="B"),
    ]

    assert (
        await delivery.load_proof_card_context(
            request=delivery.TournamentProofCardContextRequest(
                session=object(),
                parsed_tournament_id=tournament.id,
                user_id=None,
            ),
            services=delivery.TournamentProofCardContextServices(
                tournaments_repo=SimpleNamespace(get_by_id=_async_return(None)),
                participants_repo=object(),
                users_repo=object(),
                format_points_fn=str,
                format_tournament_format_fn=str,
                format_user_label_fn=lambda **_kwargs: "label",
            ),
        )
        is None
    )

    context = await delivery.load_proof_card_context(
        request=delivery.TournamentProofCardContextRequest(
            session=object(),
            parsed_tournament_id=tournament.id,
            user_id=22,
        ),
        services=delivery.TournamentProofCardContextServices(
            tournaments_repo=SimpleNamespace(get_by_id=_async_return(tournament)),
            participants_repo=SimpleNamespace(list_for_tournament=_async_return(participants)),
            users_repo=SimpleNamespace(list_by_ids=_async_return(users)),
            format_points_fn=lambda value: f"{value:g}",
            format_tournament_format_fn=lambda value: value,
            format_user_label_fn=lambda username, first_name: username or first_name,
        ),
    )

    assert context is not None
    assert [item.user_id for item in context.participants] == [22]
    assert context.participants_total == 2
    assert context.telegram_targets == {11: 101, 22: 102}


@pytest.mark.asyncio
async def test_deliver_proof_cards_sends_cached_and_rendered_cards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = tournament_row(status="COMPLETED", current_round=3)
    rows = [
        participant_row(tournament_id=tournament.id, user_id=11),
        participant_row(tournament_id=tournament.id, user_id=22),
    ]
    rows[0].proof_card_file_id = "cached-file"
    context = _context(tournament=tournament, participants=rows)
    bot = _Bot()
    repo = _ParticipantsRepo(rows)
    monkeypatch.setattr(sender, "BufferedInputFile", lambda content, filename: (content, filename))

    result = await delivery.deliver_proof_cards(
        request=delivery.TournamentProofCardDeliveryRequest(
            context=context,
            tournament_id=str(tournament.id),
            now_utc=NOW_UTC,
            explicit_resend=False,
        ),
        services=delivery.TournamentProofCardDeliveryServices(
            session_factory=SessionLocalStub(),
            participants_repo=repo,
            build_bot_fn=lambda: bot,
            build_caption_fn=lambda **kwargs: f"#{kwargs['place']} {kwargs['points']}",
            render_card_fn=lambda **_kwargs: b"png",
            logger=SimpleNamespace(
                warning=lambda *_args, **_kwargs: None, info=lambda *_args, **_kwargs: None
            ),
        ),
    )

    assert result.sent == 2
    assert result.cached_reused == 1
    assert result.failed == 0
    assert repo.sent == {11, 22}
    assert repo.file_ids == {22: "new-file"}
    assert bot.closed


@pytest.mark.asyncio
async def test_deliver_proof_cards_queues_retry_after_lock_skip() -> None:
    tournament = tournament_row(status="COMPLETED")
    row = participant_row(tournament_id=tournament.id, user_id=11)
    queued: list[dict[str, object]] = []

    def _enqueue_retry(**kwargs: object) -> bool:
        queued.append(kwargs)
        return True

    result = await delivery.deliver_proof_cards(
        request=delivery.TournamentProofCardDeliveryRequest(
            context=_context(tournament=tournament, participants=[row]),
            tournament_id=str(tournament.id),
            now_utc=NOW_UTC,
            explicit_resend=False,
        ),
        services=delivery.TournamentProofCardDeliveryServices(
            session_factory=SessionLocalStub(),
            participants_repo=SimpleNamespace(
                get_for_tournament_user_for_update=_async_return(None)
            ),
            build_bot_fn=lambda: _Bot(),
            build_caption_fn=lambda **_kwargs: "caption",
            render_card_fn=lambda **_kwargs: b"png",
            enqueue_retry_fn=_enqueue_retry,
            logger=SimpleNamespace(
                warning=lambda *_args, **_kwargs: None, info=lambda *_args, **_kwargs: None
            ),
        ),
    )

    assert result.failed == 0
    assert queued[0]["user_id"] == 11
    assert queued[0]["lock_retry_attempt"] == 1


def _context(*, tournament: Any, participants: list[Any]) -> delivery.TournamentProofCardContext:
    return delivery.TournamentProofCardContext(
        parsed_tournament_id=tournament.id,
        tournament=tournament,
        participants=participants,
        participants_total=len(participants),
        tournament_format="5 Fragen",
        standings_user_ids=[int(item.user_id) for item in participants],
        points_by_user={
            int(item.user_id): str(index) for index, item in enumerate(participants, 1)
        },
        telegram_targets={int(item.user_id): int(item.user_id) + 100 for item in participants},
        user_labels={int(item.user_id): f"U{item.user_id}" for item in participants},
    )


class _ParticipantsRepo:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = {int(row.user_id): row for row in rows}
        self.sent: set[int] = set()
        self.file_ids: dict[int, str] = {}

    async def get_for_tournament_user_for_update(self, _session, *, user_id: int, **_kwargs):
        return self._rows[user_id]

    async def set_proof_card_sent(self, _session, *, user_id: int, **_kwargs) -> None:
        self.sent.add(user_id)

    async def set_proof_card_file_id_if_missing(
        self, _session, *, user_id: int, file_id: str, **_kwargs
    ) -> None:
        self.file_ids[user_id] = file_id


class _Bot:
    def __init__(self) -> None:
        self.closed = False
        self.session = SimpleNamespace(close=self._close)

    async def send_photo(self, **_kwargs):
        return SimpleNamespace(photo=[SimpleNamespace(file_id="new-file")])

    async def _close(self) -> None:
        self.closed = True


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
