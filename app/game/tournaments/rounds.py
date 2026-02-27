from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.game.sessions.service import GameSessionService
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_PENDING,
    TOURNAMENT_MATCH_STATUS_WALKOVER,
    TOURNAMENT_MODE_CODE,
    rounds_for_tournament_format,
)
from app.game.tournaments.internal import participants_to_swiss
from app.game.tournaments.pairing import build_swiss_pairs


def collect_previous_pairs(*, matches: list[TournamentMatch]) -> set[frozenset[int]]:
    previous_pairs: set[frozenset[int]] = set()
    for match in matches:
        if match.user_b is None:
            continue
        previous_pairs.add(frozenset((int(match.user_a), int(match.user_b))))
    return previous_pairs


async def create_round_matches(
    session: AsyncSession,
    *,
    tournament: Tournament,
    round_no: int,
    participants: list[TournamentParticipant],
    previous_pairs: set[frozenset[int]],
    deadline: datetime,
    now_utc: datetime,
) -> int:
    swiss_pairs = build_swiss_pairs(
        participants=participants_to_swiss(participants),
        previous_pairs=previous_pairs,
    )
    duel_rounds = rounds_for_tournament_format(format_code=tournament.format)
    matches: list[TournamentMatch] = []

    for pair in swiss_pairs:
        match_id = uuid4()
        if pair.user_b is None:
            await TournamentParticipantsRepo.apply_score_delta(
                session,
                tournament_id=tournament.id,
                user_id=pair.user_a,
                score_delta=Decimal("1"),
                tie_break_delta=Decimal("0"),
            )
            matches.append(
                TournamentMatch(
                    id=match_id,
                    tournament_id=tournament.id,
                    round_no=round_no,
                    user_a=pair.user_a,
                    user_b=None,
                    friend_challenge_id=None,
                    status=TOURNAMENT_MATCH_STATUS_WALKOVER,
                    winner_id=pair.user_a,
                    deadline=deadline,
                )
            )
            continue

        challenge = await GameSessionService.create_tournament_match_friend_challenge(
            session,
            creator_user_id=pair.user_a,
            opponent_user_id=int(pair.user_b),
            mode_code=TOURNAMENT_MODE_CODE,
            total_rounds=duel_rounds,
            tournament_match_id=match_id,
            now_utc=now_utc,
            expires_at=deadline,
        )
        matches.append(
            TournamentMatch(
                id=match_id,
                tournament_id=tournament.id,
                round_no=round_no,
                user_a=pair.user_a,
                user_b=int(pair.user_b),
                friend_challenge_id=challenge.challenge_id,
                status=TOURNAMENT_MATCH_STATUS_PENDING,
                winner_id=None,
                deadline=deadline,
            )
        )

    await TournamentMatchesRepo.create_many(session, matches=matches)
    return len(matches)
