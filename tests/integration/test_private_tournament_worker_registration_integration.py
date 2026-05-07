from __future__ import annotations

from tests.integration.private_tournament_worker_integration_support import (
    UTC,
    SessionLocal,
    TournamentsRepo,
    _create_user,
    _ensure_tournament_schema,
    as_any_dict,
    create_private_tournament,
    datetime,
    join_private_tournament_by_code,
    pytest,
    timedelta,
    tournaments_async,
)


@pytest.mark.asyncio
async def test_worker_cancels_expired_registration_with_enough_participants(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
    await _ensure_tournament_schema()

    creator_user_id = await _create_user("private_tournament_expired_reg_creator")
    opponent_user_id = await _create_user("private_tournament_expired_reg_opponent")

    async with SessionLocal.begin() as session:
        tournament = await create_private_tournament(
            session,
            created_by=creator_user_id,
            format_code="QUICK_5",
            now_utc=now_utc,
            registration_deadline=now_utc + timedelta(minutes=5),
        )
        await join_private_tournament_by_code(
            session,
            user_id=opponent_user_id,
            invite_code=tournament.invite_code,
            now_utc=now_utc,
        )
        tournament_row = await TournamentsRepo.get_by_id_for_update(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert tournament_row is not None
        tournament_row.registration_deadline = now_utc - timedelta(minutes=1)

    monkeypatch.setattr(
        tournaments_async,
        "enqueue_private_tournament_round_messaging",
        lambda *, tournament_id: None,
    )
    monkeypatch.setattr(
        tournaments_async,
        "enqueue_private_tournament_proof_cards",
        lambda *, tournament_id: None,
    )

    result = as_any_dict(await tournaments_async.run_private_tournament_rounds_async(batch_size=20))
    assert int(result["registration_closed_total"]) == 1
    assert int(result["rounds_started_total"]) == 0
    assert int(result["tournaments_completed_total"]) == 0

    async with SessionLocal.begin() as session:
        tournament_row = await TournamentsRepo.get_by_id_for_update(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert tournament_row is not None
        assert tournament_row.status == "CANCELED"
        assert tournament_row.round_deadline is None
