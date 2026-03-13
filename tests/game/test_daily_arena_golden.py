from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments import daily_cup_user_status
from app.game.tournaments.constants import (
    DAILY_CUP_TOURNAMENT_TYPES,
    TOURNAMENT_TYPE_DAILY_ARENA,
    TOURNAMENT_TYPE_PRIVATE,
)
from app.game.tournaments.create_join import join_daily_cup_by_id
from app.game.tournaments.daily_cup_user_status import DailyCupUserStatus
from app.game.tournaments.errors import TournamentAccessError, TournamentClosedError
from app.game.tournaments.queries import get_daily_cup_lobby_by_id
from app.workers.celery_app import celery_app
from app.workers.tasks import daily_cup_core, daily_cup_messaging, daily_cup_proof_cards
from app.workers.tasks.daily_cup_schedule import configure_daily_cup_schedule
from tests.game.daily_arena_golden_support import (
    DummyBot,
    async_return,
    create_completed_daily_arena,
    create_daily_tournament,
    create_user,
    create_users,
    patch_status_window,
    prepare_tournament_db,
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


@pytest.mark.asyncio
async def test_daily_arena_join_does_not_raise_for_valid_data() -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await prepare_tournament_db()
    user_id = await create_user("golden_daily_arena_join")
    tournament_id = await create_daily_tournament(
        tournament_type=TOURNAMENT_TYPE_DAILY_ARENA,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        result = await join_daily_cup_by_id(
            session,
            user_id=user_id,
            tournament_id=tournament_id,
            now_utc=now_utc,
        )

    assert result.joined_now is True
    assert result.snapshot.type == TOURNAMENT_TYPE_DAILY_ARENA


@pytest.mark.asyncio
async def test_daily_arena_lobby_query_returns_only_daily_arena_tournaments() -> None:
    # GOLDEN: оновлено після видалення Elimination (крок 8)
    # Lobby query ізольована від інших типів турнірів
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await prepare_tournament_db()
    viewer_user_id = await create_user("golden_daily_arena_lobby")
    arena_id = await create_daily_tournament(
        tournament_type=TOURNAMENT_TYPE_DAILY_ARENA,
        now_utc=now_utc,
    )
    private_id = await create_daily_tournament(
        tournament_type=TOURNAMENT_TYPE_PRIVATE,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        arena_lobby = await get_daily_cup_lobby_by_id(
            session, tournament_id=arena_id, viewer_user_id=viewer_user_id
        )
        with pytest.raises(TournamentAccessError):
            await get_daily_cup_lobby_by_id(
                session,
                tournament_id=private_id,
                viewer_user_id=viewer_user_id,
            )

    assert arena_lobby.tournament.type == TOURNAMENT_TYPE_DAILY_ARENA


@pytest.mark.asyncio
async def test_daily_arena_join_raises_when_registration_is_already_closed() -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await prepare_tournament_db()
    user_id = await create_user("golden_daily_arena_closed")
    tournament_id = await create_daily_tournament(
        tournament_type=TOURNAMENT_TYPE_DAILY_ARENA,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        tournament.status = "ROUND_1"

    async with SessionLocal.begin() as session:
        with pytest.raises(TournamentClosedError):
            await join_daily_cup_by_id(
                session,
                user_id=user_id,
                tournament_id=tournament_id,
                now_utc=now_utc,
            )


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


@pytest.mark.asyncio
async def test_daily_arena_messaging_accepts_arena_tournament_id_without_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    now_utc = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    await prepare_tournament_db()
    user_ids = await create_users("golden_daily_arena_msg", 2)
    tournament_id = await create_completed_daily_arena(now_utc=now_utc, user_ids=user_ids)
    bot = DummyBot()
    followups: list[str] = []

    async def _fake_deliver(**kwargs) -> dict[str, object]:
        del kwargs
        return {
            "sent": 0,
            "edited": 0,
            "failed": 0,
            "new_message_ids": {},
            "replaced_message_ids": {},
        }

    monkeypatch.setattr(daily_cup_messaging, "build_bot", lambda: bot)
    monkeypatch.setattr(daily_cup_messaging, "deliver_daily_cup_messages", _fake_deliver)
    monkeypatch.setattr(
        daily_cup_messaging,
        "handle_daily_cup_completion_followups",
        lambda **kwargs: followups.append(str(kwargs["tournament_id"])),
    )

    result = await daily_cup_messaging.run_daily_cup_round_messaging_async(
        tournament_id=tournament_id
    )

    assert result["processed"] == 1
    assert result["participants_total"] == 2
    assert bot.session.closed is True
    assert followups == [tournament_id]


@pytest.mark.asyncio
async def test_daily_arena_proof_card_generation_does_not_fail_for_arena_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    now_utc = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    await prepare_tournament_db()
    user_id = await create_user("golden_daily_arena_proof")
    tournament_id = await create_completed_daily_arena(now_utc=now_utc, user_ids=[user_id])
    bot = DummyBot()

    async def _fake_send_proof_card(**kwargs) -> tuple[bool, bool, str | None]:
        del kwargs
        return True, False, "proof-file-id"

    async def _fake_get_max_round_no(*args, **kwargs) -> int:
        del args, kwargs
        return 3

    monkeypatch.setattr(daily_cup_proof_cards, "build_bot", lambda: bot)
    monkeypatch.setattr(daily_cup_proof_cards, "send_daily_cup_proof_card", _fake_send_proof_card)
    monkeypatch.setattr(
        daily_cup_proof_cards.TournamentMatchesRepo,
        "get_max_round_no",
        _fake_get_max_round_no,
    )
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "is_today_daily_cup_tournament",
        lambda **kwargs: True,
    )

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )

    assert result["processed"] == 1
    assert result["participants_total"] == 1
    assert result["sent"] == 1
    assert bot.session.closed is True
