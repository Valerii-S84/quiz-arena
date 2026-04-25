from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.bot.texts.de import TEXTS_DE
from app.db.models.energy_state import EnergyState
from app.db.models.entitlements import Entitlement
from app.db.models.quiz_questions import QuizQuestion
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import daily_cup_max_rounds_for_participants
from app.game.tournaments.daily_cup_standings import calculate_daily_cup_standings
from app.game.tournaments.settlement import settle_pending_match_from_duel
from app.workers.tasks import (
    daily_cup_async,
    daily_cup_messaging,
    daily_cup_proof_cards,
    daily_cup_rounds,
)
from tests.integration.daily_cup_proof_cards_test_support import set_user_free_energy
from tests.integration.friend_challenge_fixtures import (
    _create_user,
    _seed_friend_challenge_questions,
)
from tests.integration.test_daily_cup_worker_integration import (
    _create_daily_cup_registration_tournament,
    _ensure_tournament_schema,
    _join_users,
)
from tests.integration.test_private_tournament_worker_integration import _DummyWorkerBot

UTC = timezone.utc


class _FrozenDateTime(datetime):
    current = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)


def _build_b2_question(*, question_id: str, now_utc: datetime) -> QuizQuestion:
    return QuizQuestion(
        question_id=question_id,
        mode_code="QUICK_MIX_A1A2",
        source_file="daily_cup_b2_seed.csv",
        level="B2",
        category="DailyCupB2",
        question_text=f"B2 Frage {question_id}?",
        option_1="A",
        option_2="B",
        option_3="C",
        option_4="D",
        correct_option_id=0,
        correct_answer="A",
        explanation="Seed",
        key=question_id,
        status="ACTIVE",
        quick_mix_eligible=True,
        created_at=now_utc,
        updated_at=now_utc,
    )


async def _seed_daily_cup_b2_questions(*, now_utc: datetime) -> None:
    async with SessionLocal.begin() as session:
        session.add_all(
            [
                _build_b2_question(question_id=f"fc_b2_{index:03d}", now_utc=now_utc)
                for index in range(1, 7)
            ]
        )


async def _get_active_premium_scope(*, user_id: int) -> str | None:
    async with SessionLocal.begin() as session:
        entitlement = await session.scalar(
            select(Entitlement).where(
                Entitlement.user_id == user_id,
                Entitlement.entitlement_type == "PREMIUM",
                Entitlement.status == "ACTIVE",
            )
        )
        return None if entitlement is None else str(entitlement.scope)


async def _count_duel_tickets(*, user_id: int) -> int:
    async with SessionLocal.begin() as session:
        return await PurchasesRepo.count_credited_product(
            session,
            user_id=user_id,
            product_code="FRIEND_CHALLENGE_5",
        )


async def _get_free_energy(*, user_id: int) -> int | None:
    async with SessionLocal.begin() as session:
        state = await session.get(EnergyState, user_id)
        return None if state is None else int(state.free_energy)


async def _get_energy_balance(*, user_id: int) -> tuple[int, int] | None:
    async with SessionLocal.begin() as session:
        state = await session.get(EnergyState, user_id)
        if state is None:
            return None
        return int(state.free_energy), int(state.paid_energy)


async def _round_question_ids(*, tournament_id, round_no: int) -> tuple[tuple[str, ...], ...]:
    async with SessionLocal.begin() as session:
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=round_no,
        )
        assert matches
        question_sets: list[tuple[str, ...]] = []
        for match in matches:
            assert match.friend_challenge_id is not None
            challenge = await FriendChallengesRepo.get_by_id(session, match.friend_challenge_id)
            assert challenge is not None
            assert challenge.question_ids
            question_sets.append(tuple(str(question_id) for question_id in challenge.question_ids))
        return tuple(question_sets)


async def _settle_round_with_lowest_user_wins(
    *,
    tournament_id,
    round_no: int,
    settled_at: datetime,
) -> None:
    expired_deadline = settled_at - timedelta(minutes=1)
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        tournament.round_deadline = expired_deadline
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=round_no,
        )
        assert matches
        for match in matches:
            match.deadline = expired_deadline
            assert match.friend_challenge_id is not None
            challenge = await FriendChallengesRepo.get_by_id_for_update(
                session,
                match.friend_challenge_id,
            )
            assert challenge is not None

            if match.user_b is None:
                winner_user_id = int(match.user_a)
                challenge.status = "COMPLETED"
                challenge.winner_user_id = winner_user_id
                challenge.creator_score = 7
                challenge.opponent_score = 0
                challenge.creator_finished_at = settled_at
                challenge.opponent_finished_at = settled_at
                challenge.completed_at = settled_at
                challenge.updated_at = settled_at

                settled = await settle_pending_match_from_duel(
                    session,
                    match=match,
                    now_utc=settled_at,
                )
                assert settled is True
                continue

            winner_user_id = min(int(match.user_a), int(match.user_b))
            challenge.status = "COMPLETED"
            challenge.winner_user_id = winner_user_id
            if int(challenge.creator_user_id) == winner_user_id:
                challenge.creator_score = 7
                challenge.opponent_score = 4
            else:
                challenge.creator_score = 4
                challenge.opponent_score = 7
            challenge.creator_finished_at = settled_at
            challenge.opponent_finished_at = settled_at
            challenge.completed_at = settled_at
            challenge.updated_at = settled_at

            settled = await settle_pending_match_from_duel(
                session,
                match=match,
                now_utc=settled_at,
            )
            assert settled is True


@pytest.mark.asyncio
async def test_daily_cup_e2e_with_6_participants_reaches_completed(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_e2e6_{idx}") for idx in range(6)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    start_enqueued: list[str] = []
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(
        daily_cup_async,
        "enqueue_daily_cup_round_messaging",
        lambda *, tournament_id: start_enqueued.append(tournament_id),
    )

    started = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(started["started"]) == 1
    assert int(started["participants_total"]) == 6
    assert start_enqueued == [str(tournament_id)]

    async with SessionLocal.begin() as session:
        round_one = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        assert len(round_one) == 3
        assert all(match.status == "PENDING" for match in round_one)

    now_state = {"value": now_utc}
    round_enqueued: list[tuple[str, bool]] = []
    monkeypatch.setattr(daily_cup_rounds, "_now_utc", lambda: now_state["value"])
    monkeypatch.setattr(
        daily_cup_messaging,
        "enqueue_daily_cup_round_messaging",
        lambda *, tournament_id, enqueue_completion_followups=False: round_enqueued.append(
            (tournament_id, bool(enqueue_completion_followups))
        ),
    )

    async def _expire_and_advance(*, round_no: int, run_at: datetime) -> dict[str, int]:
        expired_deadline = run_at - timedelta(minutes=1)
        async with SessionLocal.begin() as session:
            tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
            assert tournament is not None
            tournament.round_deadline = expired_deadline
            round_matches = await TournamentMatchesRepo.list_by_tournament_round(
                session,
                tournament_id=tournament_id,
                round_no=round_no,
            )
            assert len(round_matches) == 3
            for match in round_matches:
                match.deadline = expired_deadline
        now_state["value"] = run_at
        return await daily_cup_rounds.advance_daily_cup_rounds_async()

    first_advance = await _expire_and_advance(round_no=1, run_at=now_utc + timedelta(hours=2))
    second_advance = await _expire_and_advance(round_no=2, run_at=now_utc + timedelta(hours=3))
    third_advance = await _expire_and_advance(round_no=3, run_at=now_utc + timedelta(hours=4))

    assert int(first_advance["rounds_started_total"]) >= 1
    assert int(second_advance["rounds_started_total"]) >= 1
    assert int(third_advance["tournaments_completed_total"]) >= 1
    assert round_enqueued == [
        (str(tournament_id), False),
        (str(tournament_id), False),
        (str(tournament_id), True),
    ]

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "COMPLETED"
        assert tournament.round_deadline is None
        previous_pairs: set[frozenset[int]] = set()
        for round_no in (1, 2, 3):
            matches = await TournamentMatchesRepo.list_by_tournament_round(
                session,
                tournament_id=tournament_id,
                round_no=round_no,
            )
            assert len(matches) == 3
            assert all(match.status in {"COMPLETED", "WALKOVER"} for match in matches)
            for match in matches:
                assert match.user_b is not None
                pair_key = frozenset((int(match.user_a), int(match.user_b)))
                assert pair_key not in previous_pairs
                previous_pairs.add(pair_key)


@pytest.mark.asyncio
async def test_daily_cup_e2e_covers_uniform_round_questions_winner_and_proof_cards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_e2e_proof_{idx}") for idx in range(6)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "enqueue_daily_cup_round_messaging", lambda **kwargs: None)

    started = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(started["started"]) == 1
    assert int(started["participants_total"]) == 6

    first_round_question_sets = await _round_question_ids(tournament_id=tournament_id, round_no=1)
    assert len(first_round_question_sets) == 3
    assert len(set(first_round_question_sets)) == 1

    completion_enqueues: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        daily_cup_rounds,
        "enqueue_daily_cup_completion_messaging",
        lambda *, tournament_ids, enqueue_round_messaging_fn: (
            completion_enqueues.append(tuple(tournament_ids)) if tournament_ids else None
        ),
    )

    second_round_question_sets: tuple[tuple[str, ...], ...] | None = None
    for round_no, advance_at in enumerate(
        (
            now_utc + timedelta(hours=1),
            now_utc + timedelta(hours=2),
            now_utc + timedelta(hours=3),
        ),
        start=1,
    ):
        await _settle_round_with_lowest_user_wins(
            tournament_id=tournament_id,
            round_no=round_no,
            settled_at=advance_at,
        )
        monkeypatch.setattr(daily_cup_rounds, "_now_utc", lambda current=advance_at: current)

        result = await daily_cup_rounds.advance_daily_cup_rounds_async()
        if round_no < 3:
            assert int(result["rounds_started_total"]) >= 1
            assert int(result["tournaments_completed_total"]) == 0
        else:
            assert int(result["tournaments_completed_total"]) >= 1

        if round_no == 1:
            second_round_question_sets = await _round_question_ids(
                tournament_id=tournament_id,
                round_no=2,
            )
            assert second_round_question_sets
            assert len(set(second_round_question_sets)) == 1
            assert second_round_question_sets[0] != first_round_question_sets[0]
        if round_no == 2:
            third_round_question_sets = await _round_question_ids(
                tournament_id=tournament_id,
                round_no=3,
            )
            assert third_round_question_sets
            assert len(set(third_round_question_sets)) == 1

    assert completion_enqueues == [(str(tournament_id),)]
    assert second_round_question_sets is not None

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "COMPLETED"
        standings = await calculate_daily_cup_standings(session, tournament_id=tournament_id)
        assert len(standings) == 6
        assert standings[0].user_id == min(user_ids)
        assert standings[0].wins == 6

    proof_bot = _DummyWorkerBot()
    _FrozenDateTime.current = now_utc
    monkeypatch.setattr(daily_cup_proof_cards, "datetime", _FrozenDateTime)
    monkeypatch.setattr(daily_cup_proof_cards, "build_bot", lambda: proof_bot)

    proof_result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=str(tournament_id),
        initial_delay_seconds=0,
    )

    assert proof_result == {
        "processed": 1,
        "participants_total": 6,
        "sent": 6,
        "cached_reused": 0,
        "failed": 0,
    }
    assert len(proof_bot.send_photos) == 6
    assert proof_bot.send_messages == []

    async with SessionLocal.begin() as session:
        standings = await calculate_daily_cup_standings(session, tournament_id=tournament_id)
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=tournament_id,
        )

    expected_captions = [
        f"🏆 Daily Arena Cup\nPlatz #{item.place}\nPunkte: {int(item.participant.score)}\n"
        "📱 https://t.me/Deine_Deutsch_Quiz_bot"
        for item in standings
    ]
    assert [str(item.get("caption")) for item in proof_bot.send_photos] == expected_captions
    assert all(item.proof_card_sent is True for item in participants)


@pytest.mark.asyncio
async def test_daily_cup_e2e_with_21_participants_covers_round_four_and_top_three_rewards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)
    await _seed_daily_cup_b2_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_e2e_21_{idx}") for idx in range(21)]
    tournament_id = await _create_daily_cup_registration_tournament(
        now_utc=now_utc,
        max_participants=21,
    )
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    total_rounds = daily_cup_max_rounds_for_participants(participants_total=len(user_ids))
    assert total_rounds == 4

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "enqueue_daily_cup_round_messaging", lambda **kwargs: None)
    monkeypatch.setattr(
        daily_cup_messaging,
        "enqueue_daily_cup_round_messaging",
        lambda **kwargs: None,
    )

    started = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(started["started"]) == 1
    assert int(started["participants_total"]) == 21

    question_sets_by_round: dict[int, tuple[tuple[str, ...], ...]] = {
        1: await _round_question_ids(tournament_id=tournament_id, round_no=1)
    }
    completion_enqueues: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        daily_cup_rounds,
        "enqueue_daily_cup_completion_messaging",
        lambda *, tournament_ids, enqueue_round_messaging_fn: (
            completion_enqueues.append(tuple(tournament_ids)) if tournament_ids else None
        ),
    )

    for round_no in range(1, total_rounds + 1):
        question_sets = question_sets_by_round[round_no]
        assert len(question_sets) == 11
        assert len(set(question_sets)) == 1

        advance_at = now_utc + timedelta(hours=round_no)
        await _settle_round_with_lowest_user_wins(
            tournament_id=tournament_id,
            round_no=round_no,
            settled_at=advance_at,
        )
        monkeypatch.setattr(daily_cup_rounds, "_now_utc", lambda current=advance_at: current)

        result = await daily_cup_rounds.advance_daily_cup_rounds_async()
        if round_no < total_rounds:
            assert int(result["rounds_started_total"]) >= 1
            assert int(result["tournaments_completed_total"]) == 0
            question_sets_by_round[round_no + 1] = await _round_question_ids(
                tournament_id=tournament_id,
                round_no=round_no + 1,
            )
        else:
            assert int(result["tournaments_completed_total"]) >= 1

    assert completion_enqueues == [(str(tournament_id),)]
    assert len(question_sets_by_round) == 4
    assert len({question_sets[0] for question_sets in question_sets_by_round.values()}) == 4

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "COMPLETED"
        assert tournament.current_round == 4
        standings = await calculate_daily_cup_standings(session, tournament_id=tournament_id)
        assert len(standings) == 21
        assert standings[0].user_id == min(user_ids)
        assert standings[0].wins == 8
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=tournament_id,
        )
        assert len(participants) == 21

    top_three_user_ids = [item.user_id for item in standings[:3]]
    fourth_place_user_id = standings[3].user_id
    await set_user_free_energy(user_id=top_three_user_ids[2], free_energy=18, now_utc=now_utc)
    await set_user_free_energy(user_id=fourth_place_user_id, free_energy=7, now_utc=now_utc)

    proof_bot = _DummyWorkerBot()
    _FrozenDateTime.current = now_utc
    monkeypatch.setattr(daily_cup_proof_cards, "datetime", _FrozenDateTime)
    monkeypatch.setattr(daily_cup_proof_cards, "build_bot", lambda: proof_bot)

    proof_result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=str(tournament_id),
        initial_delay_seconds=0,
    )

    assert proof_result == {
        "processed": 1,
        "participants_total": 21,
        "sent": 21,
        "cached_reused": 0,
        "failed": 0,
    }
    assert len(proof_bot.send_photos) == 21
    assert [message["text"] for message in proof_bot.send_messages] == [
        TEXTS_DE["msg.daily_cup.reward.rank_1"],
        TEXTS_DE["msg.daily_cup.reward.rank_2"],
        TEXTS_DE["msg.daily_cup.reward.rank_3"],
    ]

    assert await _get_active_premium_scope(user_id=top_three_user_ids[0]) == "PREMIUM_3_DAYS"
    assert await _count_duel_tickets(user_id=top_three_user_ids[1]) == 2
    third_place_energy = await _get_energy_balance(user_id=top_three_user_ids[2])
    assert third_place_energy == (18, 5)
    assert sum(third_place_energy) == 23
    assert await _get_active_premium_scope(user_id=fourth_place_user_id) is None
    assert await _count_duel_tickets(user_id=fourth_place_user_id) == 0
    assert await _get_free_energy(user_id=fourth_place_user_id) == 7

    async with SessionLocal.begin() as session:
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=tournament_id,
        )
    assert all(item.proof_card_sent is True for item in participants)
