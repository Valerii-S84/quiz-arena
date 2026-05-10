from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.workers.tasks import daily_cup_rounds_followups
from app.workers.tasks.tournaments_messaging_persistence import persist_standings_message_ids
from tests.workers.daily_cup_turn_reminder_test_support import session_local_with_sessions


def test_send_walkover_notifications_opens_session_per_notification(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    notifications = [
        SimpleNamespace(
            tournament_id="t1",
            round_no=1,
            user_a=1,
            user_b=2,
            user_a_points=3,
            user_b_points=0,
            rounds_total=4,
            tournament_registration_deadline=datetime(2026, 1, 1, tzinfo=timezone.utc),
            next_round_start_time=None,
        ),
        SimpleNamespace(
            tournament_id="t2",
            round_no=2,
            user_a=3,
            user_b=4,
            user_a_points=0,
            user_b_points=3,
            rounds_total=4,
            tournament_registration_deadline=None,
            next_round_start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    ]

    async def _send(session, **kwargs) -> None:
        calls.append({"session": session, **kwargs})

    monkeypatch.setattr(
        daily_cup_rounds_followups,
        "SessionLocal",
        session_local_with_sessions("s1", "s2"),
    )

    asyncio.run(
        daily_cup_rounds_followups.send_daily_cup_walkover_notifications(
            notifications=notifications,
            send_match_result_messages_fn=_send,
        )
    )

    assert [call["session"] for call in calls] == ["s1", "s2"]
    assert [call["tournament_id"] for call in calls] == ["t1", "t2"]


def test_enqueue_completion_messaging_and_persist_message_ids() -> None:
    enqueued: list[dict[str, object]] = []
    daily_cup_rounds_followups.enqueue_daily_cup_completion_messaging(
        tournament_ids=["a", "b"],
        enqueue_round_messaging_fn=lambda **kwargs: enqueued.append(kwargs),
    )
    assert enqueued == [
        {"tournament_id": "a", "enqueue_completion_followups": True},
        {"tournament_id": "b", "enqueue_completion_followups": True},
    ]

    class _Repo:
        def __init__(self) -> None:
            self.missing: list[dict[str, object]] = []
            self.replaced: list[dict[str, object]] = []

        async def set_standings_message_id_if_missing(self, _session, **kwargs) -> None:
            self.missing.append(kwargs)

        async def set_standings_message_id(self, _session, **kwargs) -> None:
            self.replaced.append(kwargs)

    repo = _Repo()
    tournament_id = uuid4()
    asyncio.run(
        persist_standings_message_ids(
            session="session",
            parsed_tournament_id=tournament_id,
            participants_repo=repo,
            new_message_ids={1: 10},
            replaced_message_ids={2: 20},
        )
    )

    assert repo.missing == [{"tournament_id": tournament_id, "user_id": 1, "message_id": 10}]
    assert repo.replaced == [{"tournament_id": tournament_id, "user_id": 2, "message_id": 20}]
