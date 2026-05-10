from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.workers.tasks.daily_cup_proof_cards_runtime import (
    grant_daily_cup_winner_rewards_once,
    load_daily_cup_proof_cards_runtime_context,
)
from tests.workers.daily_cup_turn_reminder_test_support import session_local_with_sessions


def test_runtime_context_delegates_with_session_and_repos() -> None:
    tournament_id = uuid4()
    session = object()
    captured: dict[str, object] = {}

    async def _load_context(**kwargs):
        captured.update(kwargs)
        return "context"

    result = asyncio.run(
        load_daily_cup_proof_cards_runtime_context(
            parsed_tournament_id=tournament_id,
            user_id=7,
            now_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            logger=object(),
            session_factory=session_local_with_sessions(session),
            load_context_fn=_load_context,
            tournaments_repo="tournaments",
            users_repo="users",
            matches_repo="matches",
            calculate_standings_fn="standings",
            format_points_fn="points",
            format_user_label_fn="labels",
            is_today_daily_cup_tournament_fn="today",
            daily_cup_tournament_types={"DAILY"},
            tournament_completed_status="COMPLETED",
            timezone_name="Europe/Berlin",
        )
    )

    assert result == "context"
    assert captured["session"] is session
    assert captured["parsed_tournament_id"] == tournament_id
    assert captured["user_id"] == 7
    assert captured["tournaments_repo"] == "tournaments"


def test_grant_winner_rewards_sends_notifications_and_handles_empty_rows() -> None:
    context = SimpleNamespace(parsed_tournament_id=uuid4())
    calls: list[tuple[str, object]] = []

    class _Repo:
        async def get_by_id_for_update(self, session, tournament_id):
            calls.append(("locked", session))
            assert tournament_id == context.parsed_tournament_id
            return SimpleNamespace(id=tournament_id)

    async def _grant(**kwargs):
        calls.append(("grant", kwargs["session"]))
        return ["notification"]

    async def _send(**kwargs):
        calls.append(("send", kwargs["bot"]))

    result = asyncio.run(
        grant_daily_cup_winner_rewards_once(
            bot="bot",
            context=context,
            tournament_id=str(context.parsed_tournament_id),
            now_utc=datetime.now(timezone.utc),
            logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
            session_factory=session_local_with_sessions("session"),
            tournaments_repo=_Repo(),
            grant_winner_rewards_fn=_grant,
            send_reward_messages_fn=_send,
        )
    )

    assert result == ["notification"]
    assert calls == [("locked", "session"), ("grant", "session"), ("send", "bot")]


def test_grant_winner_rewards_logs_and_returns_empty_on_exception() -> None:
    warnings: list[dict[str, object]] = []

    class _Repo:
        async def get_by_id_for_update(self, *_args):
            raise RuntimeError("db down")

    result = asyncio.run(
        grant_daily_cup_winner_rewards_once(
            bot=object(),
            context=SimpleNamespace(parsed_tournament_id=uuid4()),
            tournament_id="bad",
            now_utc=datetime.now(timezone.utc),
            logger=SimpleNamespace(
                warning=lambda event, **kwargs: warnings.append({"event": event, **kwargs})
            ),
            session_factory=session_local_with_sessions("session"),
            tournaments_repo=_Repo(),
            grant_winner_rewards_fn=None,
            send_reward_messages_fn=None,
        )
    )

    assert result == []
    assert warnings[0]["event"] == "daily_cup_winner_rewards_failed"
    assert warnings[0]["error_type"] == "RuntimeError"
