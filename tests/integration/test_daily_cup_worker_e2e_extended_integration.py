from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.bot.texts.de import TEXTS_DE
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import daily_cup_max_rounds_for_participants
from app.game.tournaments.daily_cup_standings import calculate_daily_cup_standings
from app.workers.tasks import (
    daily_cup_async,
    daily_cup_messaging,
    daily_cup_proof_cards,
    daily_cup_rounds,
)
from tests.integration.daily_cup_proof_cards_test_support import set_user_free_energy
from tests.integration.daily_cup_worker_e2e_test_support import (
    FrozenWorkerDateTime,
    count_duel_tickets,
    get_active_premium_scope,
    get_energy_balance,
    get_free_energy,
    round_question_ids,
    seed_daily_cup_b2_questions,
    settle_round_with_lowest_user_wins,
)
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


async def _assert_daily_cup_progressed_to_next_round(
    *,
    tournament_id,
    completed_round_no: int,
) -> tuple[tuple[str, ...], ...]:
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status != "COMPLETED"
        assert int(tournament.current_round) >= completed_round_no + 1

    next_round_question_sets = await round_question_ids(
        tournament_id=tournament_id,
        round_no=completed_round_no + 1,
    )
    assert next_round_question_sets
    return next_round_question_sets


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

    first_round_question_sets = await round_question_ids(tournament_id=tournament_id, round_no=1)
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
        await settle_round_with_lowest_user_wins(
            tournament_id=tournament_id,
            round_no=round_no,
            settled_at=advance_at,
        )
        monkeypatch.setattr(daily_cup_rounds, "_now_utc", lambda current=advance_at: current)

        result = await daily_cup_rounds.advance_daily_cup_rounds_async()
        if round_no < 3:
            assert int(result["tournaments_completed_total"]) == 0
            next_round_question_sets = await _assert_daily_cup_progressed_to_next_round(
                tournament_id=tournament_id,
                completed_round_no=round_no,
            )

        if round_no == 1:
            second_round_question_sets = next_round_question_sets
            assert second_round_question_sets
            assert len(set(second_round_question_sets)) == 1
            assert second_round_question_sets[0] != first_round_question_sets[0]
        if round_no == 2:
            third_round_question_sets = next_round_question_sets
            assert third_round_question_sets
            assert len(set(third_round_question_sets)) == 1

    assert completion_enqueues in ([], [(str(tournament_id),)])
    assert second_round_question_sets is not None

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "COMPLETED"
        standings = await calculate_daily_cup_standings(session, tournament_id=tournament_id)
        assert len(standings) == 6
        assert standings[0].user_id == min(user_ids)
        assert standings[0].wins == int(standings[0].participant.score)
        assert standings[0].wins >= standings[1].wins

    proof_bot = _DummyWorkerBot()
    FrozenWorkerDateTime.current = now_utc
    monkeypatch.setattr(daily_cup_proof_cards, "datetime", FrozenWorkerDateTime)
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
    await seed_daily_cup_b2_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_e2e_21_{idx}") for idx in range(21)]
    tournament_id = await _create_daily_cup_registration_tournament(
        now_utc=now_utc,
        max_participants=21,
    )
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    assert daily_cup_max_rounds_for_participants(participants_total=len(user_ids)) == 4

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "enqueue_daily_cup_round_messaging", lambda **kwargs: None)
    monkeypatch.setattr(
        daily_cup_messaging, "enqueue_daily_cup_round_messaging", lambda **kwargs: None
    )

    started = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(started["started"]) == 1
    assert int(started["participants_total"]) == 21

    question_sets_by_round: dict[int, tuple[tuple[str, ...], ...]] = {
        1: await round_question_ids(tournament_id=tournament_id, round_no=1)
    }
    completion_enqueues: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        daily_cup_rounds,
        "enqueue_daily_cup_completion_messaging",
        lambda *, tournament_ids, enqueue_round_messaging_fn: (
            completion_enqueues.append(tuple(tournament_ids)) if tournament_ids else None
        ),
    )

    for round_no in range(1, 5):
        question_sets = question_sets_by_round[round_no]
        assert len(question_sets) == 11
        assert len(set(question_sets)) == 1

        advance_at = now_utc + timedelta(hours=round_no)
        await settle_round_with_lowest_user_wins(
            tournament_id=tournament_id,
            round_no=round_no,
            settled_at=advance_at,
        )
        monkeypatch.setattr(daily_cup_rounds, "_now_utc", lambda current=advance_at: current)

        result = await daily_cup_rounds.advance_daily_cup_rounds_async()
        if round_no < 4:
            assert int(result["tournaments_completed_total"]) == 0
            question_sets_by_round[round_no + 1] = await _assert_daily_cup_progressed_to_next_round(
                tournament_id=tournament_id,
                completed_round_no=round_no,
            )

    assert completion_enqueues in ([], [(str(tournament_id),)])
    assert len({question_sets[0] for question_sets in question_sets_by_round.values()}) == 4

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "COMPLETED"
        assert tournament.current_round == 4
        standings = await calculate_daily_cup_standings(session, tournament_id=tournament_id)
        assert len(standings) == 21
        assert standings[0].user_id == min(user_ids)
        assert standings[0].wins == int(standings[0].participant.score)
        assert standings[0].wins >= standings[1].wins
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=tournament_id,
        )
        assert len(participants) == 21

    top_three_user_ids = [item.user_id for item in standings[:3]]
    fourth_place_user_id = standings[3].user_id
    await set_user_free_energy(user_id=top_three_user_ids[2], free_energy=8, now_utc=now_utc)
    await set_user_free_energy(user_id=fourth_place_user_id, free_energy=7, now_utc=now_utc)

    proof_bot = _DummyWorkerBot()
    FrozenWorkerDateTime.current = now_utc
    monkeypatch.setattr(daily_cup_proof_cards, "datetime", FrozenWorkerDateTime)
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

    assert await get_active_premium_scope(user_id=top_three_user_ids[0]) == "PREMIUM_3_DAYS"
    assert await count_duel_tickets(user_id=top_three_user_ids[1]) == 2
    third_place_energy = await get_energy_balance(user_id=top_three_user_ids[2])
    assert third_place_energy == (8, 5)
    assert sum(third_place_energy) == 13
    assert await get_active_premium_scope(user_id=fourth_place_user_id) is None
    assert await count_duel_tickets(user_id=fourth_place_user_id) == 0
    assert await get_free_energy(user_id=fourth_place_user_id) == 7

    async with SessionLocal.begin() as session:
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=tournament_id,
        )
    assert all(item.proof_card_sent is True for item in participants)
