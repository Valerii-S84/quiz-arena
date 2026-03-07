from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.game.sessions.service.friend_challenges_tournament import (
    create_tournament_match_friend_challenge,
)
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_PENDING,
    TOURNAMENT_MODE_CODE,
    TOURNAMENT_STATUS_BRACKET_LIVE,
    rounds_for_tournament_format,
)
from app.game.tournaments.pairing import create_elimination_bracket
from app.workers.tasks.daily_cup_time import get_daily_elimination_deadline_utc


def _slot_player(slot_payload: dict[str, int | bool | None]) -> int | None:
    raw = slot_payload.get("player_id")
    return None if raw is None else int(raw)


def _slot_id(slot_payload: dict[str, int | bool | None]) -> int:
    raw = slot_payload.get("slot_id")
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    return 0


def _extract_slot_payloads(bracket: dict[str, object]) -> list[dict[str, int | bool | None]]:
    raw_slots = bracket.get("slots")
    if not isinstance(raw_slots, list):
        return []
    slot_payloads: list[dict[str, int | bool | None]] = []
    for raw_slot in raw_slots:
        if isinstance(raw_slot, dict):
            slot_payloads.append(cast(dict[str, int | bool | None], raw_slot))
    return slot_payloads


async def _create_round_one_match(
    session: AsyncSession,
    *,
    tournament: Tournament,
    now_utc: datetime,
    deadline: datetime,
    slot_a: dict[str, int | bool | None],
    slot_b: dict[str, int | bool | None],
) -> TournamentMatch | None:
    player_a = _slot_player(slot_a)
    player_b = _slot_player(slot_b)
    if player_a is None and player_b is None:
        return None
    match_id = uuid4()
    duel_rounds = rounds_for_tournament_format(format_code=tournament.format)
    if player_a is not None and player_b is not None:
        challenge = await create_tournament_match_friend_challenge(
            session,
            creator_user_id=player_a,
            opponent_user_id=player_b,
            tournament_id=tournament.id,
            tournament_round_no=1,
            mode_code=TOURNAMENT_MODE_CODE,
            total_rounds=duel_rounds,
            tournament_match_id=match_id,
            now_utc=now_utc,
            expires_at=deadline,
            preferred_levels_by_round=None,
        )
        return TournamentMatch(
            id=match_id,
            tournament_id=tournament.id,
            round_no=1,
            round_number=1,
            user_a=player_a,
            user_b=player_b,
            bracket_slot_a=_slot_id(slot_a),
            bracket_slot_b=_slot_id(slot_b),
            friend_challenge_id=challenge.challenge_id,
            match_timeout_task_id=None,
            player_a_finished_at=None,
            player_b_finished_at=None,
            status=TOURNAMENT_MATCH_STATUS_PENDING,
            winner_id=None,
            deadline=deadline,
        )
    human_player = player_a if player_a is not None else player_b
    if human_player is None:
        return None
    human_slot = _slot_id(slot_a if player_a is not None else slot_b)
    bye_slot = _slot_id(slot_b if player_a is not None else slot_a)
    challenge = await create_tournament_match_friend_challenge(
        session,
        creator_user_id=int(human_player),
        opponent_user_id=int(human_player),
        tournament_id=tournament.id,
        tournament_round_no=1,
        mode_code=TOURNAMENT_MODE_CODE,
        total_rounds=duel_rounds,
        tournament_match_id=match_id,
        now_utc=now_utc,
        expires_at=deadline,
        preferred_levels_by_round=None,
    )
    return TournamentMatch(
        id=match_id,
        tournament_id=tournament.id,
        round_no=1,
        round_number=1,
        user_a=int(human_player),
        user_b=None,
        bracket_slot_a=human_slot,
        bracket_slot_b=bye_slot,
        friend_challenge_id=challenge.challenge_id,
        match_timeout_task_id=None,
        player_a_finished_at=None,
        player_b_finished_at=None,
        status=TOURNAMENT_MATCH_STATUS_PENDING,
        winner_id=None,
        deadline=deadline,
    )


async def start_daily_elimination_bracket(
    session: AsyncSession,
    *,
    tournament: Tournament,
    participants: list[TournamentParticipant],
    now_utc: datetime,
) -> int:
    participant_ids = [int(item.user_id) for item in participants]
    bracket = create_elimination_bracket(participant_ids, tournament_id=tournament.id)
    tournament.bracket = bracket
    tournament.current_round = 1
    tournament.status = TOURNAMENT_STATUS_BRACKET_LIVE
    deadline = get_daily_elimination_deadline_utc(now_utc=now_utc)
    tournament.round_deadline = deadline
    slot_payloads = _extract_slot_payloads(bracket)
    matches: list[TournamentMatch] = []
    for slot_index in range(0, len(slot_payloads), 2):
        match = await _create_round_one_match(
            session,
            tournament=tournament,
            now_utc=now_utc,
            deadline=deadline,
            slot_a=slot_payloads[slot_index],
            slot_b=slot_payloads[slot_index + 1],
        )
        if match is not None:
            matches.append(match)
    await TournamentMatchesRepo.create_many(session, matches=matches)
    return len(matches)
