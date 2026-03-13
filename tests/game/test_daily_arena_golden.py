from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.game.tournaments import daily_cup_user_status
from app.game.tournaments.constants import DAILY_CUP_TOURNAMENT_TYPES, TOURNAMENT_TYPE_DAILY_ARENA
from app.game.tournaments.daily_cup_user_status import DailyCupUserStatus
from app.workers.celery_app import celery_app
from app.workers.tasks import daily_cup_core
from app.workers.tasks.daily_cup_schedule import configure_daily_cup_schedule
from tests.game.daily_arena_golden_support import (
    async_return,
    patch_status_window,
    reload_daily_cup_config,
    status_tournament,
)


def test_daily_arena_constants_include_only_arena_type() -> None:
    # GOLDEN: оновлено після видалення Elimination (крок 8)
    # DAILY_CUP_TOURNAMENT_TYPES містить тільки DAILY_ARENA
    assert TOURNAMENT_TYPE_DAILY_ARENA in DAILY_CUP_TOURNAMENT_TYPES


@pytest.mark.parametrize(
    ("env_value"),
    [None, TOURNAMENT_TYPE_DAILY_ARENA],
    ids=["default_env", "explicit_arena_env"],
)
def test_daily_arena_config_resolves_to_arena(
    monkeypatch: pytest.MonkeyPatch,
    env_value: str | None,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    module = reload_daily_cup_config(monkeypatch, env_value)
    assert module.DAILY_CUP_TOURNAMENT_TYPE == TOURNAMENT_TYPE_DAILY_ARENA


@pytest.mark.asyncio
async def test_daily_arena_core_always_uses_arena_type_no_fallback_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: оновлено після видалення Elimination fallback (крок 4)
    # DAILY_ARENA єдиний тип, fallback логіка свідомо видалена
    created = {}
    now_utc = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    window = SimpleNamespace(close_at_utc=now_utc)

    async def _fake_get(*args, **kwargs):
        del args, kwargs
        return None

    async def _fake_lock(*args, **kwargs) -> None:
        del args, kwargs

    async def _fake_create(session, *, tournament):
        del session
        created["tournament"] = tournament
        return tournament

    async def _fake_invite_code(session) -> str:
        del session
        return "golden-invite"

    monkeypatch.setattr(daily_cup_core, "_lock_daily_cup_registration_slot", _fake_lock)
    monkeypatch.setattr(daily_cup_core, "get_daily_cup_window", lambda *, now_utc: window)
    monkeypatch.setattr(
        daily_cup_core.TournamentsRepo,
        "get_by_type_and_registration_deadline_for_update",
        _fake_get,
    )
    monkeypatch.setattr(daily_cup_core.TournamentsRepo, "create", _fake_create)
    monkeypatch.setattr(daily_cup_core, "generate_invite_code", _fake_invite_code)

    tournament = await daily_cup_core.ensure_daily_cup_registration_tournament(
        session=SimpleNamespace(),
        now_utc_value=now_utc,
    )

    assert tournament.type == TOURNAMENT_TYPE_DAILY_ARENA
    assert tournament.name == "Daily Arena Cup"
    assert created["tournament"].max_participants == daily_cup_core.TOURNAMENT_MAX_PARTICIPANTS


@pytest.mark.asyncio
async def test_daily_arena_status_returns_round_active_for_pending_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    patch_status_window(monkeypatch)
    tournament = status_tournament(status="ROUND_1", current_round=1)

    monkeypatch.setattr(
        daily_cup_user_status.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        async_return(tournament),
    )
    monkeypatch.setattr(
        daily_cup_user_status.TournamentParticipantsRepo,
        "list_for_tournament",
        async_return([SimpleNamespace(user_id=101)]),
    )
    monkeypatch.setattr(
        daily_cup_user_status.TournamentMatchesRepo,
        "list_by_tournament_round",
        async_return([SimpleNamespace(user_a=101, user_b=202, status="PENDING")]),
    )

    snapshot = await daily_cup_user_status.get_daily_cup_status_for_user(
        SimpleNamespace(),
        user_id=101,
        now_utc=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
    )

    assert snapshot.status is DailyCupUserStatus.ROUND_ACTIVE
    assert snapshot.tournament.type == TOURNAMENT_TYPE_DAILY_ARENA


@pytest.mark.asyncio
async def test_daily_arena_status_returns_no_tournament_when_row_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    patch_status_window(monkeypatch)
    monkeypatch.setattr(
        daily_cup_user_status.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        async_return(None),
    )

    snapshot = await daily_cup_user_status.get_daily_cup_status_for_user(
        SimpleNamespace(),
        user_id=101,
        now_utc=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
    )

    assert snapshot.status is DailyCupUserStatus.NO_TOURNAMENT
    assert snapshot.tournament is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("participant_ids", "expected_status"),
    [
        ([101], DailyCupUserStatus.REGISTERED_WAITING),
        ([202], DailyCupUserStatus.INVITE_OPEN),
    ],
    ids=["registered_user", "unregistered_user"],
)
async def test_daily_arena_status_registration_variants(
    monkeypatch: pytest.MonkeyPatch,
    participant_ids: list[int],
    expected_status: DailyCupUserStatus,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    patch_status_window(monkeypatch)

    monkeypatch.setattr(
        daily_cup_user_status.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        async_return(status_tournament(status="REGISTRATION")),
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


def test_daily_arena_schedule_snapshot_contains_only_arena_entries() -> None:
    # GOLDEN: оновлено після видалення Elimination (крок 1 рефакторингу)
    # daily-elimination-final-deadline свідомо видалений з beat schedule
    celery_app_stub = SimpleNamespace(conf=SimpleNamespace(beat_schedule={}))
    configure_daily_cup_schedule(celery_app_stub)
    schedule = celery_app_stub.conf.beat_schedule
    assert "daily-cup-send-invite-registration" in schedule
    assert "daily-cup-last-call-reminder" in schedule
    assert "daily-cup-prestart-reminder" in schedule
    assert "daily-cup-close-registration" in schedule
    assert "daily-cup-publish-final-results" in schedule
    assert "daily-cup-round-advance" in schedule


def test_daily_arena_task_names_are_registered_in_celery_app() -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    from app.workers.tasks import daily_cup as daily_cup_tasks

    assert daily_cup_tasks is not None
    task_names = set(celery_app.tasks.keys())
    assert "app.workers.tasks.daily_cup.send_invite_registration" in task_names
    assert "app.workers.tasks.daily_cup.close_registration_and_start" in task_names
    assert "app.workers.tasks.daily_cup.advance_rounds" in task_names
    assert "app.workers.tasks.daily_cup.publish_final_results" in task_names
    assert "app.workers.tasks.daily_cup.run_daily_cup_round_messaging" in task_names
    assert "app.workers.tasks.daily_cup.run_daily_cup_proof_cards" in task_names
