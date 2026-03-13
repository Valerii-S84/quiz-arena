from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.game.tournaments import daily_cup_user_status
from app.game.tournaments.constants import (
    TOURNAMENT_STATUS_COMPLETED,
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_TYPE_DAILY_ARENA,
)
from app.game.tournaments.daily_cup_user_status import DailyCupUserStatus
from app.workers.tasks import daily_cup_messaging
from tests.game.daily_arena_golden_support import (
    DummyBot,
    async_return,
    close_coroutine_and_raise,
    close_coroutine_with_name,
    make_standing_row,
    make_worker_user,
    patch_status_window,
    session_local_with_sessions,
    status_tournament,
)


def _arena_tournament(*, status: str, current_round: int = 0) -> SimpleNamespace:
    tournament = status_tournament(status=status, current_round=current_round)
    tournament.round_deadline = datetime(2026, 3, 1, 18, 30, tzinfo=UTC)
    return tournament


def _empty_daily_cup_result() -> dict[str, int]:
    return {"processed": 0, "participants_total": 0, "sent": 0, "edited": 0, "failed": 0}


@pytest.mark.parametrize(
    ("raw_value", "defaults", "expected"),
    [
        ("bad", (16, 0), (16, 0)),
        ("25:99", (18, 0), (18, 0)),
        ("09:45", (0, 0), (9, 45)),
    ],
    ids=["broken", "out_of_range", "valid"],
)
def test_daily_arena_status_time_helpers_keep_current_parsing_rules(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    defaults: tuple[int, int],
    expected: tuple[int, int],
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    monkeypatch.setattr(daily_cup_user_status.settings, "daily_cup_timezone", "Europe/Berlin")
    monkeypatch.setattr(
        daily_cup_user_status,
        "DAILY_CUP_TOURNAMENT_TYPE",
        TOURNAMENT_TYPE_DAILY_ARENA,
    )
    monkeypatch.setenv("DAILY_CUP_INVITE_TIME", "broken")
    monkeypatch.setenv("DAILY_CUP_CLOSE_TIME", "25:99")

    assert (
        daily_cup_user_status._parse_hhmm(
            raw_value, default_hour=defaults[0], default_minute=defaults[1]
        )
        == expected
    )

    now_utc = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    anchor = daily_cup_user_status._local_daily_cup_anchor(now_utc=now_utc, hour=16, minute=0)

    assert anchor.hour == 16
    assert anchor.minute == 0
    assert anchor.tzinfo is not None
    assert daily_cup_user_status._invite_open_at_utc(now_utc=now_utc) == datetime(
        2026, 3, 1, 15, 0, tzinfo=UTC
    )
    assert daily_cup_user_status._close_at_utc(now_utc=now_utc) == datetime(
        2026, 3, 1, 17, 0, tzinfo=UTC
    )


@pytest.mark.asyncio
async def test_daily_arena_status_returns_no_tournament_before_invite_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    monkeypatch.setattr(
        daily_cup_user_status,
        "_invite_open_at_utc",
        lambda *, now_utc: now_utc + timedelta(minutes=1),
    )

    async def _unexpected_lookup(*args, **kwargs):
        del args, kwargs
        pytest.fail("unexpected tournament lookup before invite window")

    monkeypatch.setattr(
        daily_cup_user_status.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        _unexpected_lookup,
    )

    snapshot = await daily_cup_user_status.get_daily_cup_status_for_user(
        SimpleNamespace(),
        user_id=101,
        now_utc=datetime(2026, 3, 1, 16, 0, tzinfo=UTC),
    )

    assert snapshot.status is DailyCupUserStatus.NO_TOURNAMENT
    assert snapshot.tournament is None


@pytest.mark.asyncio
async def test_daily_arena_status_returns_not_participant_for_active_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    patch_status_window(monkeypatch)
    monkeypatch.setattr(
        daily_cup_user_status.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        async_return(_arena_tournament(status="ROUND_2", current_round=2)),
    )
    monkeypatch.setattr(
        daily_cup_user_status.TournamentParticipantsRepo,
        "list_for_tournament",
        async_return([SimpleNamespace(user_id=202)]),
    )

    snapshot = await daily_cup_user_status.get_daily_cup_status_for_user(
        SimpleNamespace(),
        user_id=101,
        now_utc=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
    )

    assert snapshot.status is DailyCupUserStatus.NOT_PARTICIPANT


@pytest.mark.asyncio
async def test_daily_arena_status_returns_round_waiting_without_pending_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    patch_status_window(monkeypatch)
    monkeypatch.setattr(
        daily_cup_user_status.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        async_return(_arena_tournament(status="ROUND_2", current_round=2)),
    )
    monkeypatch.setattr(
        daily_cup_user_status.TournamentParticipantsRepo,
        "list_for_tournament",
        async_return([SimpleNamespace(user_id=101)]),
    )
    monkeypatch.setattr(
        daily_cup_user_status.TournamentMatchesRepo,
        "list_by_tournament_round",
        async_return([SimpleNamespace(user_a=101, user_b=202, status="COMPLETED")]),
    )

    snapshot = await daily_cup_user_status.get_daily_cup_status_for_user(
        SimpleNamespace(),
        user_id=101,
        now_utc=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
    )

    assert snapshot.status is DailyCupUserStatus.ROUND_WAITING


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tournament_status", "participant_ids", "expected_status", "expect_tournament"),
    [
        (TOURNAMENT_STATUS_COMPLETED, [101], DailyCupUserStatus.COMPLETED, True),
        (TOURNAMENT_STATUS_COMPLETED, [202], DailyCupUserStatus.NOT_PARTICIPANT, True),
        ("PAUSED", [101], DailyCupUserStatus.NO_TOURNAMENT, False),
    ],
    ids=["completed_participant", "completed_outsider", "unknown_status"],
)
async def test_daily_arena_status_completed_and_fallback_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    tournament_status: str,
    participant_ids: list[int],
    expected_status: DailyCupUserStatus,
    expect_tournament: bool,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    patch_status_window(monkeypatch)
    tournament = _arena_tournament(status=tournament_status, current_round=3)
    monkeypatch.setattr(
        daily_cup_user_status.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        async_return(tournament),
    )
    monkeypatch.setattr(
        daily_cup_user_status.TournamentParticipantsRepo,
        "list_for_tournament",
        async_return([SimpleNamespace(user_id=user_id) for user_id in participant_ids]),
    )

    snapshot = await daily_cup_user_status.get_daily_cup_status_for_user(
        SimpleNamespace(),
        user_id=101,
        now_utc=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
    )

    assert snapshot.status is expected_status
    assert (snapshot.tournament is not None) is expect_tournament


@pytest.mark.asyncio
async def test_daily_arena_messaging_returns_empty_for_invalid_tournament_id() -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    result = await daily_cup_messaging.run_daily_cup_round_messaging_async(
        tournament_id="not-a-uuid"
    )
    assert result == _empty_daily_cup_result()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tournament", "standings", "expected"),
    [
        (None, [make_standing_row(user_id=101, place=1)], _empty_daily_cup_result()),
        (
            _arena_tournament(status=TOURNAMENT_STATUS_REGISTRATION),
            [make_standing_row(user_id=101, place=1)],
            _empty_daily_cup_result(),
        ),
        (_arena_tournament(status=TOURNAMENT_STATUS_COMPLETED), [], _empty_daily_cup_result()),
    ],
    ids=["missing_tournament", "registration_state", "empty_participants"],
)
async def test_daily_arena_messaging_short_circuits_when_pipeline_has_no_work(
    monkeypatch: pytest.MonkeyPatch,
    tournament: SimpleNamespace | None,
    standings: list[SimpleNamespace],
    expected: dict[str, int],
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    monkeypatch.setattr(
        daily_cup_messaging,
        "SessionLocal",
        session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(daily_cup_messaging.TournamentsRepo, "get_by_id", async_return(tournament))
    monkeypatch.setattr(
        daily_cup_messaging, "calculate_daily_cup_standings", async_return(standings)
    )

    result = await daily_cup_messaging.run_daily_cup_round_messaging_async(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    )

    assert result == expected


@pytest.mark.asyncio
async def test_daily_arena_messaging_round_pipeline_fetches_round_matches_for_arena(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    tournament = _arena_tournament(status="ROUND_2", current_round=2)
    standings = [
        make_standing_row(user_id=101, place=1, score="4", tie_break="7"),
        make_standing_row(user_id=202, place=2, score="3", tie_break="6"),
    ]
    calls: dict[str, object] = {}
    bot = DummyBot()

    async def _fake_round_matches(session, *, tournament_id, round_no):
        del session, tournament_id
        calls["round_no"] = round_no
        return [SimpleNamespace(friend_challenge_id="arena-round")]

    async def _fake_deliver(**kwargs):
        calls["deliver"] = kwargs
        return {
            "sent": 2,
            "edited": 0,
            "failed": 0,
            "new_message_ids": {101: 1001},
            "replaced_message_ids": {},
        }

    async def _fake_persist(**kwargs) -> None:
        calls["persist"] = kwargs

    monkeypatch.setattr(
        daily_cup_messaging,
        "SessionLocal",
        session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(daily_cup_messaging.TournamentsRepo, "get_by_id", async_return(tournament))
    monkeypatch.setattr(
        daily_cup_messaging, "calculate_daily_cup_standings", async_return(standings)
    )
    monkeypatch.setattr(
        daily_cup_messaging.UsersRepo,
        "list_by_ids",
        async_return([make_worker_user(user_id=101), make_worker_user(user_id=202)]),
    )
    monkeypatch.setattr(
        daily_cup_messaging.TournamentMatchesRepo,
        "list_by_tournament_round",
        _fake_round_matches,
    )
    monkeypatch.setattr(daily_cup_messaging, "build_bot", lambda: bot)
    monkeypatch.setattr(daily_cup_messaging, "deliver_daily_cup_messages", _fake_deliver)
    monkeypatch.setattr(
        daily_cup_messaging,
        "persist_daily_cup_standings_message_ids",
        _fake_persist,
    )
    monkeypatch.setattr(
        daily_cup_messaging,
        "handle_daily_cup_completion_followups",
        lambda **kwargs: calls.setdefault("followups", kwargs),
    )

    result = await daily_cup_messaging.run_daily_cup_round_messaging_async_with_followups(
        tournament_id=str(tournament.id),
        enqueue_completion_followups=True,
    )

    assert result == {"processed": 1, "participants_total": 2, "sent": 2, "edited": 0, "failed": 0}
    assert calls["round_no"] == 2
    assert calls["deliver"]["tournament"].type == TOURNAMENT_TYPE_DAILY_ARENA
    assert calls["persist"]["new_message_ids"] == {101: 1001}
    assert calls["followups"]["is_completed"] is False
    assert bot.session.closed is True


def test_daily_arena_messaging_enqueue_paths_and_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    enqueued: dict[str, object] = {}

    monkeypatch.setattr(
        daily_cup_messaging,
        "is_celery_task",
        lambda task: task is daily_cup_messaging.run_daily_cup_round_messaging,
    )
    monkeypatch.setattr(
        daily_cup_messaging.run_daily_cup_round_messaging,
        "delay",
        lambda **kwargs: enqueued.setdefault("delay", kwargs),
    )
    daily_cup_messaging.enqueue_daily_cup_round_messaging(
        tournament_id="arena-id",
        enqueue_completion_followups=True,
    )
    assert enqueued["delay"] == {
        "tournament_id": "arena-id",
        "enqueue_completion_followups": True,
    }

    monkeypatch.setattr(daily_cup_messaging, "is_celery_task", lambda task: False)
    monkeypatch.setattr(
        daily_cup_messaging,
        "run_async_job",
        lambda coroutine: enqueued.setdefault(
            "run_async_job", close_coroutine_with_name(coroutine)
        ),
    )
    daily_cup_messaging.enqueue_daily_cup_round_messaging(tournament_id="arena-id-async")
    assert enqueued["run_async_job"] == "run_daily_cup_round_messaging_async_with_followups"

    warnings: list[dict[str, object]] = []
    monkeypatch.setattr(
        daily_cup_messaging,
        "run_async_job",
        lambda coroutine: close_coroutine_and_raise(coroutine, RuntimeError("boom")),
    )
    monkeypatch.setattr(
        daily_cup_messaging.logger,
        "warning",
        lambda event, **kwargs: warnings.append({"event": event, **kwargs}),
    )
    daily_cup_messaging.enqueue_daily_cup_round_messaging(tournament_id="arena-id-failed")
    assert warnings == [
        {
            "event": "daily_cup_round_message_enqueue_failed",
            "tournament_id": "arena-id-failed",
            "error_type": "RuntimeError",
        }
    ]

    monkeypatch.setattr(
        daily_cup_messaging,
        "run_async_job",
        lambda coroutine: {"wrapped": close_coroutine_with_name(coroutine)},
    )
    wrapped = daily_cup_messaging.run_daily_cup_round_messaging(tournament_id="arena-id-wrapper")
    assert wrapped == {"wrapped": "run_daily_cup_round_messaging_async_with_followups"}
