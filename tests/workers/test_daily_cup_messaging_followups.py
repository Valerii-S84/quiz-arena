from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.workers.tasks import daily_cup_nonfinishers_summary, daily_cup_proof_cards
from app.workers.tasks.daily_cup_messaging_followups import handle_daily_cup_completion_followups

UTC = timezone.utc


class _RecordingLogger:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def info(self, event: str, **kwargs) -> None:
        self.calls.append({"event": event, **kwargs})


@pytest.mark.parametrize(
    ("is_completed", "enqueue_completion_followups"),
    [
        (False, True),
        (True, False),
    ],
)
def test_handle_daily_cup_completion_followups_returns_without_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    is_completed: bool,
    enqueue_completion_followups: bool,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    logger = _RecordingLogger()

    monkeypatch.setattr(
        daily_cup_proof_cards,
        "enqueue_daily_cup_proof_cards",
        lambda **kwargs: calls.append(("proof_cards", kwargs)),
    )
    monkeypatch.setattr(
        daily_cup_nonfinishers_summary,
        "enqueue_daily_cup_nonfinishers_summary",
        lambda **kwargs: calls.append(("nonfinishers", kwargs)),
    )

    handle_daily_cup_completion_followups(
        is_completed=is_completed,
        enqueue_completion_followups=enqueue_completion_followups,
        allow_completion_followups=True,
        tournament_id="t-1",
        registration_deadline=None,
        logger=logger,
    )

    assert calls == []
    assert logger.calls == []


def test_handle_daily_cup_completion_followups_enqueues_followup_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        daily_cup_proof_cards,
        "enqueue_daily_cup_proof_cards",
        lambda **kwargs: calls.append(("proof_cards", kwargs)),
    )
    monkeypatch.setattr(
        daily_cup_nonfinishers_summary,
        "enqueue_daily_cup_nonfinishers_summary",
        lambda **kwargs: calls.append(("nonfinishers", kwargs)),
    )

    handle_daily_cup_completion_followups(
        is_completed=True,
        enqueue_completion_followups=True,
        allow_completion_followups=True,
        tournament_id="t-2",
        registration_deadline=None,
        logger=_RecordingLogger(),
    )

    assert calls == [
        ("proof_cards", {"tournament_id": "t-2", "delay_seconds": 2}),
        ("nonfinishers", {"tournament_id": "t-2"}),
    ]


def test_handle_daily_cup_completion_followups_logs_stale_skip() -> None:
    registration_deadline = datetime(2026, 3, 14, 8, 30, tzinfo=UTC)
    logger = _RecordingLogger()

    handle_daily_cup_completion_followups(
        is_completed=True,
        enqueue_completion_followups=True,
        allow_completion_followups=False,
        tournament_id="t-3",
        registration_deadline=registration_deadline,
        logger=logger,
    )

    assert logger.calls == [
        {
            "event": "daily_cup_completion_followups_skipped_stale_tournament",
            "tournament_id": "t-3",
            "registration_deadline": registration_deadline.isoformat(),
        }
    ]
