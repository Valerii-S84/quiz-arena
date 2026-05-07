from __future__ import annotations

from tests.integration.private_tournament_worker_integration_support import (
    UTC,
    FriendChallengesRepo,
    SessionLocal,
    TournamentMatchesRepo,
    TournamentsRepo,
    _create_user,
    _ensure_tournament_schema,
    _seed_friend_challenge_questions,
    as_any_dict,
    create_private_tournament,
    datetime,
    join_private_tournament_by_code,
    pytest,
    start_private_tournament,
    timedelta,
    tournaments_async,
)


@pytest.mark.asyncio
async def test_worker_marks_tournament_completed_after_round_three_deadline(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    creator_user_id = await _create_user("private_tournament_worker_final_creator")
    opponent_user_id = await _create_user("private_tournament_worker_final_opponent")

    async with SessionLocal.begin() as session:
        tournament = await create_private_tournament(
            session,
            created_by=creator_user_id,
            format_code="QUICK_5",
            now_utc=now_utc,
        )
        await join_private_tournament_by_code(
            session,
            user_id=opponent_user_id,
            invite_code=tournament.invite_code,
            now_utc=now_utc,
        )
        await start_private_tournament(
            session,
            creator_user_id=creator_user_id,
            tournament_id=tournament.tournament_id,
            now_utc=now_utc,
        )
        round_one_matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament.tournament_id,
            round_no=1,
        )
        assert len(round_one_matches) == 1
        match = round_one_matches[0]
        assert match.friend_challenge_id is not None

        challenge = await FriendChallengesRepo.get_by_id_for_update(
            session, match.friend_challenge_id
        )
        assert challenge is not None
        challenge.status = "COMPLETED"
        challenge.winner_user_id = creator_user_id
        challenge.creator_score = 4
        challenge.opponent_score = 1
        challenge.creator_finished_at = now_utc
        challenge.opponent_finished_at = now_utc
        challenge.completed_at = now_utc
        challenge.updated_at = now_utc

        tournament_row = await TournamentsRepo.get_by_id_for_update(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert tournament_row is not None
        tournament_row.current_round = 3
        tournament_row.status = "ROUND_3"
        tournament_row.round_deadline = now_utc - timedelta(minutes=1)
        match.round_no = 3
        match.deadline = now_utc - timedelta(minutes=1)

    enqueued_rounds: list[str] = []
    enqueued_proofs: list[str] = []
    monkeypatch.setattr(
        tournaments_async,
        "enqueue_private_tournament_round_messaging",
        lambda *, tournament_id: enqueued_rounds.append(tournament_id),
    )
    monkeypatch.setattr(
        tournaments_async,
        "enqueue_private_tournament_proof_cards",
        lambda *, tournament_id: enqueued_proofs.append(tournament_id),
    )

    result = as_any_dict(await tournaments_async.run_private_tournament_rounds_async(batch_size=20))
    assert int(result["tournaments_completed_total"]) >= 1
    assert enqueued_rounds == [str(tournament.tournament_id)]
    assert enqueued_proofs == [str(tournament.tournament_id)]

    async with SessionLocal.begin() as session:
        tournament_row = await TournamentsRepo.get_by_id_for_update(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert tournament_row is not None
        assert tournament_row.status == "COMPLETED"
        assert tournament_row.round_deadline is None
