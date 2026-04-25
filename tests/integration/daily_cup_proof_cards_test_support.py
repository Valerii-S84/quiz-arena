from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.db.models.entitlements import Entitlement
from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournament_round_scores_repo import (
    TournamentRoundScorePayload,
    TournamentRoundScoresRepo,
)
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.economy.energy.service import EnergyService
from app.workers.tasks import daily_cup_proof_cards
from app.workers.tasks.daily_cup_config import DAILY_CUP_TIMEZONE
from tests.integration.friend_challenge_fixtures import _create_user
from tests.integration.test_private_tournament_worker_integration import (
    _DummyWorkerBot,
    _ensure_tournament_schema,
)

UTC = timezone.utc


def fixed_daily_cup_now() -> datetime:
    return (
        datetime.now(UTC)
        .astimezone(ZoneInfo(DAILY_CUP_TIMEZONE))
        .replace(hour=12, minute=0, second=0, microsecond=0)
        .astimezone(UTC)
    )


async def ensure_tournament_schema() -> None:
    await _ensure_tournament_schema()


async def create_daily_cup_users(*, prefix: str, count: int) -> list[int]:
    return [await _create_user(f"{prefix}_{index}") for index in range(count)]


def install_recording_worker_bot(
    monkeypatch: pytest.MonkeyPatch,
    *,
    record_renders: bool = False,
) -> tuple[_DummyWorkerBot, list[dict[str, object]]]:
    bot = _DummyWorkerBot()
    render_calls: list[dict[str, object]] = []

    monkeypatch.setattr(daily_cup_proof_cards, "build_bot", lambda: bot)
    if record_renders:

        def _fake_render(**kwargs: object) -> bytes:
            render_calls.append(kwargs)
            return b"png"

        monkeypatch.setattr(
            daily_cup_proof_cards,
            "render_tournament_proof_card_png",
            _fake_render,
        )

    return bot, render_calls


def _build_round_matches(
    *,
    tournament_id: UUID,
    user_ids: list[int],
    rounds_played: int,
    now_utc: datetime,
) -> list[TournamentMatch]:
    matches: list[TournamentMatch] = []
    for round_number in range(1, rounds_played + 1):
        matches.append(
            TournamentMatch(
                id=uuid4(),
                tournament_id=tournament_id,
                round_no=round_number,
                round_number=None,
                user_a=user_ids[0],
                user_b=user_ids[1] if len(user_ids) > 1 else None,
                bracket_slot_a=None,
                bracket_slot_b=None,
                friend_challenge_id=None,
                match_timeout_task_id=None,
                player_a_finished_at=None,
                player_b_finished_at=None,
                status="COMPLETED",
                winner_id=user_ids[0],
                deadline=now_utc - timedelta(minutes=round_number),
            )
        )
    return matches


async def create_completed_daily_cup(*, now_utc: datetime, user_ids: list[int]) -> str:
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.create(
            session,
            tournament=Tournament(
                id=uuid4(),
                type="DAILY_ARENA",
                created_by=None,
                name="Daily Arena Cup",
                status="COMPLETED",
                format="QUICK_5",
                max_participants=max(8, len(user_ids)),
                current_round=3,
                registration_deadline=now_utc - timedelta(hours=5),
                round_deadline=None,
                invite_code=uuid4().hex[:12],
                created_at=now_utc - timedelta(hours=6),
            ),
        )
        for user_id in user_ids:
            await TournamentParticipantsRepo.create_once(
                session,
                tournament_id=tournament.id,
                user_id=user_id,
                joined_at=now_utc - timedelta(hours=4),
            )
        session.add_all(
            _build_round_matches(
                tournament_id=tournament.id,
                user_ids=user_ids,
                rounds_played=3,
                now_utc=now_utc,
            )
        )
        participants = await TournamentParticipantsRepo.list_for_tournament_for_update(
            session,
            tournament_id=tournament.id,
        )
        assert len(participants) == len(user_ids)
        for index, row in enumerate(participants):
            row.score = Decimal(len(user_ids) - index)
            row.tie_break = Decimal(index)
        return str(tournament.id)


async def create_completed_daily_cup_with_seeded_scores(
    *,
    now_utc: datetime,
    user_ids: list[int],
) -> str:
    round_specs: dict[int, tuple[tuple[int, int, int], ...]] = {
        user_ids[0]: ((2, 7, 700), (2, 6, 650), (2, 6, 600), (2, 5, 550)),
        user_ids[1]: ((2, 6, 750), (2, 6, 700), (2, 5, 650), (1, 5, 600)),
        user_ids[2]: ((2, 6, 800), (1, 5, 750), (2, 5, 700), (1, 4, 650)),
        user_ids[3]: ((2, 5, 850), (1, 5, 800), (1, 4, 750), (1, 4, 700)),
        user_ids[4]: ((2, 5, 900), (1, 4, 850), (1, 4, 800), (0, 4, 750)),
        user_ids[5]: ((1, 4, 950), (1, 4, 900), (1, 4, 850), (0, 3, 800)),
        user_ids[6]: ((1, 4, 1000), (1, 3, 950), (0, 3, 900), (0, 3, 850)),
        user_ids[7]: ((1, 3, 1050), (0, 3, 1000), (0, 3, 950), (0, 2, 900)),
        user_ids[8]: ((0, 2, 1100), (0, 2, 1050), (0, 2, 1000), (0, 2, 950)),
    }

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.create(
            session,
            tournament=Tournament(
                id=uuid4(),
                type="DAILY_ARENA",
                created_by=None,
                name="Daily Arena Cup",
                status="COMPLETED",
                format="QUICK_5",
                max_participants=100,
                current_round=4,
                registration_deadline=now_utc - timedelta(hours=5),
                round_deadline=None,
                invite_code=uuid4().hex[:12],
                created_at=now_utc - timedelta(hours=6),
            ),
        )
        for index, user_id in enumerate(user_ids):
            await TournamentParticipantsRepo.create_once(
                session,
                tournament_id=tournament.id,
                user_id=user_id,
                joined_at=now_utc - timedelta(hours=4) + timedelta(minutes=index),
            )

        for user_id, rounds in round_specs.items():
            total_points = Decimal("0")
            total_correct = Decimal("0")
            for round_number, (points, correct_answers, total_time_ms) in enumerate(
                rounds, start=1
            ):
                total_points += Decimal(points)
                total_correct += Decimal(correct_answers)
                await TournamentRoundScoresRepo.upsert_result(
                    session,
                    payload=TournamentRoundScorePayload(
                        tournament_id=tournament.id,
                        round_number=round_number,
                        player_id=user_id,
                        opponent_id=None,
                        wins=points,
                        is_draw=points == 1,
                        correct_answers=correct_answers,
                        total_time_ms=total_time_ms,
                        got_bye=False,
                        auto_finished=False,
                        created_at=now_utc,
                    ),
                )
            participant = await TournamentParticipantsRepo.get_for_tournament_user(
                session,
                tournament_id=tournament.id,
                user_id=user_id,
            )
            assert participant is not None
            participant.score = total_points
            participant.tie_break = total_correct
        session.add_all(
            _build_round_matches(
                tournament_id=tournament.id,
                user_ids=user_ids,
                rounds_played=4,
                now_utc=now_utc,
            )
        )

        return str(tournament.id)


async def create_completed_daily_cup_with_bye_seeded_scores(
    *,
    now_utc: datetime,
    user_ids: list[int],
) -> str:
    selected_user_ids = user_ids[:13]
    if len(selected_user_ids) != 13:
        raise ValueError("create_completed_daily_cup_with_bye_seeded_scores requires 13 users")

    round_specs: dict[int, tuple[tuple[int, int, int, bool], ...]] = {
        selected_user_ids[0]: ((2, 7, 700, False), (2, 6, 650, False), (2, 6, 600, False)),
        selected_user_ids[1]: ((2, 6, 710, False), (2, 6, 660, False), (1, 5, 610, False)),
        selected_user_ids[2]: ((2, 6, 720, False), (1, 5, 670, True), (1, 4, 620, False)),
        selected_user_ids[3]: ((2, 5, 730, False), (1, 5, 680, False), (0, 4, 630, False)),
        selected_user_ids[4]: ((1, 5, 740, False), (1, 4, 690, False), (1, 3, 640, False)),
        selected_user_ids[5]: ((2, 4, 750, False), (0, 4, 700, False), (0, 3, 650, False)),
        selected_user_ids[6]: ((1, 4, 760, False), (1, 3, 710, False), (0, 3, 660, False)),
        selected_user_ids[7]: ((1, 3, 770, False), (0, 3, 720, False), (0, 3, 670, False)),
        selected_user_ids[8]: ((1, 3, 780, False), (0, 3, 730, False), (0, 2, 680, False)),
        selected_user_ids[9]: ((0, 3, 790, False), (0, 2, 740, False), (0, 2, 690, False)),
        selected_user_ids[10]: ((0, 2, 800, False), (0, 2, 750, False), (0, 2, 700, False)),
        selected_user_ids[11]: ((0, 2, 810, False), (0, 2, 760, False), (0, 1, 710, False)),
        selected_user_ids[12]: ((0, 2, 820, False), (0, 1, 770, False), (0, 1, 720, False)),
    }

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.create(
            session,
            tournament=Tournament(
                id=uuid4(),
                type="DAILY_ARENA",
                created_by=None,
                name="Daily Arena Cup",
                status="COMPLETED",
                format="QUICK_5",
                max_participants=100,
                current_round=3,
                registration_deadline=now_utc - timedelta(hours=5),
                round_deadline=None,
                invite_code=uuid4().hex[:12],
                created_at=now_utc - timedelta(hours=6),
            ),
        )
        for index, user_id in enumerate(selected_user_ids):
            await TournamentParticipantsRepo.create_once(
                session,
                tournament_id=tournament.id,
                user_id=user_id,
                joined_at=now_utc - timedelta(hours=4) + timedelta(minutes=index),
            )

        session.add_all(
            [
                TournamentMatch(
                    id=uuid4(),
                    tournament_id=tournament.id,
                    round_no=1,
                    round_number=None,
                    user_a=selected_user_ids[12],
                    user_b=None,
                    bracket_slot_a=None,
                    bracket_slot_b=None,
                    friend_challenge_id=None,
                    match_timeout_task_id=None,
                    player_a_finished_at=None,
                    player_b_finished_at=None,
                    status="COMPLETED",
                    winner_id=selected_user_ids[12],
                    deadline=now_utc - timedelta(minutes=3),
                ),
                TournamentMatch(
                    id=uuid4(),
                    tournament_id=tournament.id,
                    round_no=2,
                    round_number=None,
                    user_a=selected_user_ids[2],
                    user_b=None,
                    bracket_slot_a=None,
                    bracket_slot_b=None,
                    friend_challenge_id=None,
                    match_timeout_task_id=None,
                    player_a_finished_at=None,
                    player_b_finished_at=None,
                    status="COMPLETED",
                    winner_id=selected_user_ids[2],
                    deadline=now_utc - timedelta(minutes=2),
                ),
                TournamentMatch(
                    id=uuid4(),
                    tournament_id=tournament.id,
                    round_no=3,
                    round_number=None,
                    user_a=selected_user_ids[11],
                    user_b=None,
                    bracket_slot_a=None,
                    bracket_slot_b=None,
                    friend_challenge_id=None,
                    match_timeout_task_id=None,
                    player_a_finished_at=None,
                    player_b_finished_at=None,
                    status="COMPLETED",
                    winner_id=selected_user_ids[11],
                    deadline=now_utc - timedelta(minutes=1),
                ),
            ]
        )

        for index, user_id in enumerate(selected_user_ids):
            total_points = Decimal("0")
            total_correct = Decimal("0")
            for round_number, (wins, correct_answers, total_time_ms, got_bye) in enumerate(
                round_specs[user_id], start=1
            ):
                total_points += Decimal(wins)
                total_correct += Decimal(correct_answers)
                opponent_id = None
                if not got_bye:
                    opponent_id = selected_user_ids[(index + round_number) % len(selected_user_ids)]
                    if opponent_id == user_id:
                        opponent_id = selected_user_ids[
                            (index + round_number + 1) % len(selected_user_ids)
                        ]
                await TournamentRoundScoresRepo.upsert_result(
                    session,
                    payload=TournamentRoundScorePayload(
                        tournament_id=tournament.id,
                        round_number=round_number,
                        player_id=user_id,
                        opponent_id=opponent_id,
                        wins=wins,
                        is_draw=wins == 1 and not got_bye,
                        correct_answers=correct_answers,
                        total_time_ms=total_time_ms,
                        got_bye=got_bye,
                        auto_finished=False,
                        created_at=now_utc,
                    ),
                )
            participant = await TournamentParticipantsRepo.get_for_tournament_user(
                session,
                tournament_id=tournament.id,
                user_id=user_id,
            )
            assert participant is not None
            participant.score = total_points
            participant.tie_break = total_correct

        return str(tournament.id)


async def set_user_free_energy(*, user_id: int, free_energy: int, now_utc: datetime) -> None:
    async with SessionLocal.begin() as session:
        state = await EnergyService.initialize_user_state(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )
        state.free_energy = free_energy


async def set_user_active_premium(
    *,
    user_id: int,
    scope: str,
    now_utc: datetime,
    ends_at: datetime,
) -> None:
    async with SessionLocal.begin() as session:
        session.add(
            Entitlement(
                user_id=user_id,
                entitlement_type="PREMIUM",
                scope=scope,
                status="ACTIVE",
                starts_at=now_utc,
                ends_at=ends_at,
                source_purchase_id=None,
                idempotency_key=f"test:premium:{user_id}:{scope}:{ends_at.timestamp()}",
                metadata_={"source": "test"},
                created_at=now_utc,
                updated_at=now_utc,
            )
        )
