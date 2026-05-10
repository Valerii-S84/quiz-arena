from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.game.tournaments.constants import TOURNAMENT_TYPE_PRIVATE
from app.workers.tasks.tournaments_messaging_context import load_round_messaging_context


class _TournamentsRepo:
    async def get_by_id(self, *_args):
        return SimpleNamespace(type=TOURNAMENT_TYPE_PRIVATE, status="ROUND_1", current_round=1)


class _ParticipantsRepo:
    async def list_for_tournament(self, *_args, **_kwargs):
        return [
            SimpleNamespace(user_id=3, score=9),
            SimpleNamespace(user_id=4, score=5),
        ]


class _UsersRepo:
    async def list_by_ids(self, _session, user_ids):
        return [
            SimpleNamespace(
                id=user_id, telegram_user_id=user_id * 10, username=f"u{user_id}", first_name=None
            )
            for user_id in user_ids
        ]


class _MatchesRepo:
    async def list_by_tournament_round(self, *_args, **_kwargs):
        return ["match"]


def test_load_private_tournament_round_messaging_context_builds_maps() -> None:
    tournament_id = uuid4()

    context = asyncio.run(
        load_round_messaging_context(
            session=object(),
            parsed_tournament_id=tournament_id,
            tournaments_repo=_TournamentsRepo(),
            participants_repo=_ParticipantsRepo(),
            users_repo=_UsersRepo(),
            matches_repo=_MatchesRepo(),
            format_points_fn=lambda value: f"{value}p",
            round_statuses={"ROUND_1"},
            format_user_label_fn=lambda username, first_name: username or first_name,
        )
    )

    assert context is not None
    assert context.parsed_tournament_id == tournament_id
    assert context.standings_user_ids == [3, 4]
    assert context.points_by_user == {3: "9p", 4: "5p"}
    assert context.place_by_user == {3: 1, 4: 2}
    assert context.telegram_targets == {3: 30, 4: 40}
    assert context.round_matches == ["match"]
