from __future__ import annotations

from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.game.tournaments.constants import DAILY_CUP_TOURNAMENT_TYPES
from app.game.tournaments.daily_cup_standings import calculate_daily_cup_standings


def build_tournament_post_match_text(
    *,
    challenge,
    user_id: int,
    opponent_label: str,
    place: int | None = None,
    participants_total: int | None = None,
) -> str:
    if challenge.creator_user_id == user_id:
        my_score = challenge.creator_score
        opponent_score = challenge.opponent_score
    else:
        my_score = challenge.opponent_score
        opponent_score = challenge.creator_score
    you_won = challenge.winner_user_id == user_id
    return "\n".join(
        [
            "✅ Match gespielt!",
            "",
            f"Du: {my_score}/{challenge.total_rounds} ✅",
            f"{opponent_label}: {opponent_score}/{challenge.total_rounds}",
            (
                f"📊 Aktueller Stand: Platz {place} von {participants_total}"
                if place is not None and participants_total is not None
                else ""
            ),
            "",
            "🏆 Du hast gewonnen!" if you_won else "💪 Knapp! Nächste Runde kommt.",
        ]
    )


def build_tournament_post_match_keyboard(*, tournament_id: str | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if tournament_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📊 Turnier-Tabelle",
                    callback_data=f"friend:tournament:view:{tournament_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🏠 Menü", callback_data="home:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def resolve_tournament_id_for_match(
    *,
    session_local,
    tournament_match_id: UUID,
) -> str | None:
    async with session_local.begin() as session:
        match = await TournamentMatchesRepo.get_by_id_for_update(
            session,
            tournament_match_id,
        )
    if match is None:
        return None
    return str(match.tournament_id)


async def resolve_tournament_place_for_user(
    *,
    session_local,
    tournament_match_id: UUID,
    user_id: int,
) -> tuple[int | None, int | None]:
    async with session_local.begin() as session:
        match = await TournamentMatchesRepo.get_by_id_for_update(session, tournament_match_id)
        if match is None:
            return None, None
        tournament = await TournamentsRepo.get_by_id(session, match.tournament_id)
        if tournament is None:
            return None, None
        if tournament.type in DAILY_CUP_TOURNAMENT_TYPES:
            standings = await calculate_daily_cup_standings(
                session, tournament_id=match.tournament_id
            )
            for item in standings:
                if item.user_id == user_id:
                    return item.place, len(standings)
            return None, len(standings)
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=match.tournament_id,
        )
    for place, participant in enumerate(participants, start=1):
        if int(participant.user_id) == user_id:
            return place, len(participants)
    return None, len(participants)


def enqueue_tournament_post_match_updates(*, tournament_id: str) -> None:
    from app.bot.handlers import gameplay_tournament_notifications
    from app.workers.tasks.tournaments_proof_cards import enqueue_private_tournament_proof_cards

    gameplay_tournament_notifications.enqueue_tournament_round_messaging(
        tournament_id=tournament_id
    )
    enqueue_private_tournament_proof_cards(tournament_id=tournament_id)
