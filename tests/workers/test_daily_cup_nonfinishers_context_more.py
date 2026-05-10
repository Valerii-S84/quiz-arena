from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.workers.tasks.daily_cup_nonfinishers_summary_context import (
    load_daily_cup_nonfinishers_summary_context,
)


class _TournamentsRepo:
    async def get_by_id(self, *_args):
        return SimpleNamespace(type="DAILY", status="COMPLETED")


class _ParticipantsRepo:
    async def list_for_tournament(self, *_args, **_kwargs):
        return [SimpleNamespace(user_id=1), SimpleNamespace(user_id=2)]


class _UsersRepo:
    async def list_by_ids(self, _session, user_ids):
        return [SimpleNamespace(id=user_id, telegram_user_id=user_id * 10) for user_id in user_ids]


class _MatchesRepo:
    def __init__(self, challenge_id) -> None:
        self.challenge_id = challenge_id

    async def get_max_round_no(self, *_args, **_kwargs):
        return 2

    async def list_by_tournament_round(self, *_args, **kwargs):
        if kwargs["round_no"] == 1:
            return [SimpleNamespace(friend_challenge_id=self.challenge_id)]
        return [SimpleNamespace(friend_challenge_id=None)]


class _Session:
    def __init__(self, challenge) -> None:
        self.challenge = challenge

    async def execute(self, _statement):
        challenge = self.challenge

        class _Scalars:
            def all(self):
                return [challenge]

        return SimpleNamespace(scalars=lambda: _Scalars())


def test_load_nonfinishers_context_collects_challenges_and_targets() -> None:
    tournament_id = uuid4()
    challenge_id = uuid4()
    challenge = SimpleNamespace(id=challenge_id)

    context = asyncio.run(
        load_daily_cup_nonfinishers_summary_context(
            session=_Session(challenge),
            parsed_tournament_id=tournament_id,
            tournaments_repo=_TournamentsRepo(),
            participants_repo=_ParticipantsRepo(),
            users_repo=_UsersRepo(),
            matches_repo=_MatchesRepo(challenge_id),
            daily_cup_tournament_types={"DAILY"},
            tournament_completed_status="COMPLETED",
            collect_nonfinishers_fn=lambda **kwargs: (
                {1, 99} if kwargs["challenges_by_id"] == {challenge_id: challenge} else set()
            ),
        )
    )

    assert context is not None
    assert context.participants_total == 2
    assert context.nonfinishers == [1]
    assert context.telegram_targets == {1: 10, 2: 20}


def test_load_nonfinishers_context_returns_none_for_empty_or_invalid() -> None:
    class _EmptyParticipantsRepo:
        async def list_for_tournament(self, *_args, **_kwargs):
            return []

    assert (
        asyncio.run(
            load_daily_cup_nonfinishers_summary_context(
                session=object(),
                parsed_tournament_id=uuid4(),
                tournaments_repo=_TournamentsRepo(),
                participants_repo=_EmptyParticipantsRepo(),
                users_repo=_UsersRepo(),
                matches_repo=_MatchesRepo(uuid4()),
                daily_cup_tournament_types={"DAILY"},
                tournament_completed_status="COMPLETED",
                collect_nonfinishers_fn=lambda **_kwargs: set(),
            )
        )
        is None
    )
