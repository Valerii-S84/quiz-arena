from app.workers.tasks import tournaments


def test_run_private_tournament_rounds_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, batch_size: int, round_duration_hours: int) -> dict[str, int]:
        return {
            "batch_size": batch_size,
            "registration_closed_total": 1,
            "rounds_started_total": 1,
            "tournaments_completed_total": 0,
            "matches_settled_total": 2,
            "matches_created_total": 2,
            "round_duration_hours": round_duration_hours,
        }

    monkeypatch.setattr(tournaments, "run_private_tournament_rounds_async", fake_async)

    result = tournaments.run_private_tournament_rounds(batch_size=7, round_duration_hours=12)
    assert result["batch_size"] == 7
    assert result["round_duration_hours"] == 12
