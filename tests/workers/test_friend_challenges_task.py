from app.workers.tasks import friend_challenges


def test_run_friend_challenge_deadlines_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, batch_size: int) -> dict[str, int]:
        return {
            "batch_size": batch_size,
            "last_chance_queued_total": 2,
            "expired_total": 1,
            "last_chance_sent_total": 2,
            "last_chance_failed_total": 0,
            "expired_notice_sent_total": 2,
            "expired_notice_failed_total": 0,
        }

    monkeypatch.setattr(friend_challenges, "run_friend_challenge_deadlines_async", fake_async)

    result = friend_challenges.run_friend_challenge_deadlines(batch_size=7)
    assert result["batch_size"] == 7
    assert result["last_chance_queued_total"] == 2


def test_format_remaining_hhmm_clamps_negative_values() -> None:
    from datetime import datetime, timedelta, timezone

    now_utc = datetime.now(timezone.utc)
    hours, minutes = friend_challenges._format_remaining_hhmm(
        now_utc=now_utc,
        expires_at=now_utc - timedelta(minutes=5),
    )
    assert (hours, minutes) == (0, 0)
