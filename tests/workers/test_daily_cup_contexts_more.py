from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.workers.tasks.daily_cup_messaging_context import load_daily_cup_round_messaging_context
from app.workers.tasks.daily_cup_proof_cards_context import load_daily_cup_proof_cards_context


class _TournamentsRepo:
    def __init__(self, tournament: object | None) -> None:
        self.tournament = tournament

    async def get_by_id(self, *_args):
        return self.tournament


class _UsersRepo:
    async def list_by_ids(self, _session, user_ids):
        return [
            SimpleNamespace(
                id=user_id,
                username=f"user{user_id}",
                first_name=None,
                telegram_user_id=user_id * 10,
            )
            for user_id in user_ids
        ]


def _standing(user_id: int, score: int, place: int):
    return SimpleNamespace(
        user_id=user_id,
        place=place,
        participant=SimpleNamespace(user_id=user_id, score=score, tie_break=place),
    )


def test_daily_cup_messaging_context_builds_completed_followup_context() -> None:
    tournament_id = uuid4()
    tournament = SimpleNamespace(
        type="DAILY",
        status="COMPLETED",
        current_round=2,
        registration_deadline=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    async def _standings(*_args, **_kwargs):
        return [_standing(1, 7, 1), _standing(2, 5, 2)]

    class _MatchesRepo:
        async def list_by_tournament_round(self, *_args, **_kwargs):
            return ["match"]

    context = asyncio.run(
        load_daily_cup_round_messaging_context(
            session=object(),
            parsed_tournament_id=tournament_id,
            now_utc_value=datetime(2026, 1, 1, tzinfo=timezone.utc),
            tournaments_repo=_TournamentsRepo(tournament),
            matches_repo=_MatchesRepo(),
            users_repo=_UsersRepo(),
            calculate_standings_fn=_standings,
            format_points_fn=lambda value: f"{value}p",
            format_user_label_fn=lambda username, first_name: username or first_name,
            is_today_daily_cup_tournament_fn=lambda **_kwargs: True,
            daily_cup_tournament_types={"DAILY"},
            round_statuses={"COMPLETED"},
            timezone_name="Europe/Berlin",
        )
    )

    assert context is not None
    assert context.is_completed is True
    assert context.allow_completion_followups is True
    assert context.round_matches == ["match"]
    assert context.points_by_user == {1: "7p", 2: "5p"}
    assert context.place_by_user == {1: 1, 2: 2}


def test_daily_cup_proof_cards_context_filters_single_user_and_rounds() -> None:
    tournament_id = uuid4()
    logs: list[str] = []

    async def _standings(*_args, **_kwargs):
        return [_standing(1, 7, 1), _standing(2, 5, 2)]

    class _MatchesRepo:
        async def get_max_round_no(self, *_args, **_kwargs):
            return 4

    context = asyncio.run(
        load_daily_cup_proof_cards_context(
            session=object(),
            parsed_tournament_id=tournament_id,
            user_id=2,
            now_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            tournaments_repo=_TournamentsRepo(
                SimpleNamespace(
                    type="DAILY",
                    status="COMPLETED",
                    registration_deadline=datetime(2026, 1, 1, tzinfo=timezone.utc),
                )
            ),
            users_repo=_UsersRepo(),
            matches_repo=_MatchesRepo(),
            calculate_standings_fn=_standings,
            format_points_fn=lambda value: str(value),
            format_user_label_fn=lambda username, first_name: username or first_name,
            is_today_daily_cup_tournament_fn=lambda **_kwargs: True,
            logger=SimpleNamespace(info=lambda event, **_kwargs: logs.append(event)),
            daily_cup_tournament_types={"DAILY"},
            tournament_completed_status="COMPLETED",
            timezone_name="Europe/Berlin",
        )
    )

    assert context is not None
    assert [row.user_id for row in context.participants] == [2]
    assert context.participants_total == 2
    assert context.rounds_played == 4
    assert logs == []
