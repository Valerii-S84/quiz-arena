import pytest

from app.workers.tasks import daily_challenge, daily_challenge_async


def test_run_daily_question_set_precompute_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, object]:
        return {"berlin_date": "2026-02-26", "questions_total": 7}

    monkeypatch.setattr(daily_challenge, "run_daily_question_set_precompute_async", fake_async)

    result = daily_challenge.run_daily_question_set_precompute()
    assert result == {"berlin_date": "2026-02-26", "questions_total": 7}


def test_run_daily_push_notifications_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, batch_size: int, push_kind: str) -> dict[str, object]:
        return {
            "batch_size": batch_size,
            "push_kind": push_kind,
            "sent_total": 5,
            "skipped_total": 1,
        }

    monkeypatch.setattr(daily_challenge, "run_daily_push_notifications_async", fake_async)

    result = daily_challenge.run_daily_push_notifications(batch_size=50)
    assert result == {
        "batch_size": 50,
        "push_kind": "MORNING",
        "sent_total": 5,
        "skipped_total": 1,
    }


@pytest.mark.parametrize(
    ("current_streak", "expected_tag"),
    [
        (0, 1),
        (4, 5),
    ],
)
def test_build_push_text_uses_next_streak_day_with_minimum_one(
    current_streak: int,
    expected_tag: int,
) -> None:
    text = daily_challenge_async._build_push_text(
        push_kind="MORNING",
        current_streak=current_streak,
    )

    assert text == (
        f"🔥 Tag {expected_tag}! Deine Challenge wartet. Beantworte 7/7 → Duell-Ticket 🎟"
    )
