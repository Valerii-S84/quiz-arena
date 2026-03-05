from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.game.sessions.service.friend_challenges_tournament import create_tournament_match_friend_challenge
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_PENDING,
    TOURNAMENT_MODE_CODE,
    TOURNAMENT_STATUS_BRACKET_LIVE,
    TOURNAMENT_STATUS_COMPLETED,
    TOURNAMENT_TYPE_DAILY_ELIMINATION,
    rounds_for_tournament_format,
)


def _to_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _match_round_number(match: TournamentMatch) -> int:
    return max(1, int(match.round_number or match.round_no))


def _match_index(match: TournamentMatch) -> int:
    slot_a = int(match.bracket_slot_a or 0)
    slot_b = int(match.bracket_slot_b or slot_a + 1)
    return min(slot_a, slot_b) // 2


def _resolve_deadline(*, tournament: Tournament, now_utc: datetime) -> datetime:
    if tournament.round_deadline is not None:
        return tournament.round_deadline
    return now_utc + timedelta(hours=4)


def _ensure_bracket_dict(tournament: Tournament) -> dict[str, object]:
    raw = tournament.bracket if isinstance(tournament.bracket, dict) else None
    if raw is None:
        return {}
    return dict(raw)


def _ensure_round_winners(bracket: dict[str, object], *, round_number: int) -> dict[str, int]:
    winners_raw = bracket.get("winners")
    winners: dict[str, object] = winners_raw if isinstance(winners_raw, dict) else {}
    round_key = str(round_number)
    round_winners_raw = winners.get(round_key)
    round_winners: dict[str, int] = (
        {str(key): _to_int(value, default=0) for key, value in round_winners_raw.items()}
        if isinstance(round_winners_raw, dict)
        else {}
    )
    winners[round_key] = round_winners
    bracket["winners"] = winners
    return round_winners


def _set_eliminated_place(
    bracket: dict[str, object],
    *,
    loser_id: int,
    round_number: int,
) -> None:
    eliminated_raw = bracket.get("eliminated")
    eliminated: dict[str, object] = eliminated_raw if isinstance(eliminated_raw, dict) else {}
    size = max(2, _to_int(bracket.get("size", 2), default=2))
    rounds_total = max(1, _to_int(bracket.get("rounds_total", 1), default=1))
    place_hint = 2 if round_number >= rounds_total else (size // (2**round_number)) + 1
    eliminated[str(int(loser_id))] = {"round": int(round_number), "place": int(place_hint)}
    bracket["eliminated"] = eliminated


async def _create_next_round_match(
    session: AsyncSession,
    *,
    tournament: Tournament,
    now_utc: datetime,
    round_number: int,
    match_index: int,
    winner_id: int,
    sibling_winner_id: int,
) -> int:
    next_round = round_number + 1
    next_match_index = match_index // 2
    bracket_slot_a = next_match_index * 2
    bracket_slot_b = bracket_slot_a + 1
    existing = await TournamentMatchesRepo.get_by_tournament_round_slots_for_update(
        session,
        tournament_id=tournament.id,
        round_number=next_round,
        bracket_slot_a=bracket_slot_a,
        bracket_slot_b=bracket_slot_b,
    )
    if existing is not None:
        return 0
    user_a = int(winner_id if match_index % 2 == 0 else sibling_winner_id)
    user_b = int(sibling_winner_id if match_index % 2 == 0 else winner_id)
    match_id = uuid4()
    challenge = await create_tournament_match_friend_challenge(
        session,
        creator_user_id=user_a,
        opponent_user_id=user_b,
        mode_code=TOURNAMENT_MODE_CODE,
        total_rounds=rounds_for_tournament_format(format_code=tournament.format),
        tournament_match_id=match_id,
        now_utc=now_utc,
        expires_at=_resolve_deadline(tournament=tournament, now_utc=now_utc),
        preferred_levels_by_round=None,
    )
    await TournamentMatchesRepo.create_many(
        session,
        matches=[
            TournamentMatch(
                id=match_id,
                tournament_id=tournament.id,
                round_no=next_round,
                round_number=next_round,
                user_a=user_a,
                user_b=user_b,
                bracket_slot_a=bracket_slot_a,
                bracket_slot_b=bracket_slot_b,
                friend_challenge_id=challenge.challenge_id,
                match_timeout_task_id=None,
                player_a_finished_at=None,
                player_b_finished_at=None,
                status=TOURNAMENT_MATCH_STATUS_PENDING,
                winner_id=None,
                deadline=_resolve_deadline(tournament=tournament, now_utc=now_utc),
            )
        ],
    )
    tournament.current_round = max(int(tournament.current_round), next_round)
    tournament.status = TOURNAMENT_STATUS_BRACKET_LIVE
    return 1


async def complete_elimination_tournament(
    session: AsyncSession,
    *,
    tournament: Tournament,
    champion_id: int,
    finalist_id: int | None = None,
) -> dict[str, int]:
    from app.workers.tasks.daily_cup_messaging import enqueue_daily_cup_round_messaging

    bracket = _ensure_bracket_dict(tournament)
    bracket["champion_id"] = int(champion_id)
    if finalist_id is not None:
        bracket["finalist_id"] = int(finalist_id)
    tournament.bracket = bracket
    tournament.status = TOURNAMENT_STATUS_COMPLETED
    tournament.round_deadline = None
    tournament.current_round = max(
        int(tournament.current_round),
        _to_int(bracket.get("rounds_total", 1), default=1),
    )
    enqueue_daily_cup_round_messaging(tournament_id=str(tournament.id), enqueue_completion_followups=True)
    return {
        "processed": 1,
        "next_match_created": 0,
        "waiting": 0,
        "tournament_completed": 1,
    }


async def on_elimination_match_complete(
    session: AsyncSession,
    *,
    match_id: UUID,
    winner_id: int,
    loser_id: int | None,
    now_utc: datetime,
) -> dict[str, int]:
    match = await TournamentMatchesRepo.get_by_id_for_update(session, match_id)
    if match is None:
        return {"processed": 0, "next_match_created": 0, "waiting": 0, "tournament_completed": 0}
    tournament = await TournamentsRepo.get_by_id_for_update(session, match.tournament_id)
    if tournament is None or tournament.type != TOURNAMENT_TYPE_DAILY_ELIMINATION:
        return {"processed": 0, "next_match_created": 0, "waiting": 0, "tournament_completed": 0}

    bracket = _ensure_bracket_dict(tournament)
    if not bracket:
        return {"processed": 0, "next_match_created": 0, "waiting": 0, "tournament_completed": 0}
    round_number = _match_round_number(match)
    match_index = _match_index(match)
    round_winners = _ensure_round_winners(bracket, round_number=round_number)
    round_winners[str(match_index)] = int(winner_id)
    expected_round_matches = max(
        1,
        max(2, _to_int(bracket.get("size", 2), default=2)) // (2**round_number),
    )
    if len(round_winners) >= expected_round_matches:
        bracket["rounds_done"] = max(
            _to_int(bracket.get("rounds_done", 0), default=0),
            round_number,
        )
    if loser_id is not None:
        _set_eliminated_place(
            bracket,
            loser_id=int(loser_id),
            round_number=round_number,
        )
    tournament.bracket = bracket
    tournament.status = TOURNAMENT_STATUS_BRACKET_LIVE
    tournament.current_round = max(int(tournament.current_round), round_number)

    rounds_total = max(1, _to_int(bracket.get("rounds_total", 1), default=1))
    if round_number >= rounds_total:
        return await complete_elimination_tournament(
            session,
            tournament=tournament,
            champion_id=int(winner_id),
            finalist_id=(int(loser_id) if loser_id is not None else None),
        )

    sibling_winner_id = round_winners.get(str(match_index ^ 1))
    if sibling_winner_id is None:
        return {"processed": 1, "next_match_created": 0, "waiting": 1, "tournament_completed": 0}
    created = await _create_next_round_match(
        session,
        tournament=tournament,
        now_utc=now_utc,
        round_number=round_number,
        match_index=match_index,
        winner_id=int(winner_id),
        sibling_winner_id=int(sibling_winner_id),
    )
    return {
        "processed": 1,
        "next_match_created": int(created),
        "waiting": int(created == 0),
        "tournament_completed": 0,
    }
