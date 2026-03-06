from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.types import InlineQuery, InlineQueryResultCachedPhoto

from app.bot.keyboards.proof_card_share import (
    DAILY_CUP_INLINE_SHARE_PREFIX,
    FRIEND_CHALLENGE_INLINE_SHARE_PREFIX,
)
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import DAILY_CUP_TOURNAMENT_TYPES, TOURNAMENT_STATUS_COMPLETED

router = Router(name="gameplay_inline_share")


def _parse_query_id(*, query: str, prefix: str) -> UUID | None:
    if not query.startswith(prefix):
        return None
    raw_value = query.removeprefix(prefix).strip()
    try:
        return UUID(raw_value)
    except ValueError:
        return None


async def _build_daily_cup_result(*, session, user_id: int, tournament_id: UUID):
    tournament = await TournamentsRepo.get_by_id(session, tournament_id)
    if (
        tournament is None
        or tournament.type not in DAILY_CUP_TOURNAMENT_TYPES
        or tournament.status != TOURNAMENT_STATUS_COMPLETED
    ):
        return None
    participant = await TournamentParticipantsRepo.get_for_tournament_user(
        session,
        tournament_id=tournament_id,
        user_id=user_id,
    )
    if participant is None or not participant.proof_card_file_id:
        return None
    return InlineQueryResultCachedPhoto(
        id=f"daily:{tournament_id.hex}",
        photo_file_id=participant.proof_card_file_id,
        title="Daily Arena Proof Card",
        description="Teile deine Daily-Arena-Karte als Bild.",
    )


async def _build_friend_challenge_result(*, session, user_id: int, challenge_id: UUID):
    challenge = await FriendChallengesRepo.get_by_id(session, challenge_id)
    if challenge is None or challenge.status not in {"COMPLETED", "EXPIRED", "WALKOVER"}:
        return None
    if int(challenge.creator_user_id) == user_id:
        file_id = challenge.creator_proof_card_file_id
    elif challenge.opponent_user_id is not None and int(challenge.opponent_user_id) == user_id:
        file_id = challenge.opponent_proof_card_file_id
    else:
        return None
    if not file_id:
        return None
    return InlineQueryResultCachedPhoto(
        id=f"duel:{challenge_id.hex}",
        photo_file_id=file_id,
        title="Duel Proof Card",
        description="Teile deine Duell-Karte als Bild.",
    )


@router.inline_query(F.query.startswith("proof:"))
async def handle_proof_card_inline_share(inline_query: InlineQuery) -> None:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.get_by_telegram_user_id(session, inline_query.from_user.id)
        if user is None:
            await inline_query.answer([], cache_time=0, is_personal=True)
            return
        daily_tournament_id = _parse_query_id(
            query=inline_query.query,
            prefix=DAILY_CUP_INLINE_SHARE_PREFIX,
        )
        if daily_tournament_id is not None:
            result = await _build_daily_cup_result(
                session=session,
                user_id=int(user.id),
                tournament_id=daily_tournament_id,
            )
            await inline_query.answer(
                [result] if result is not None else [],
                cache_time=0,
                is_personal=True,
            )
            return

        challenge_id = _parse_query_id(
            query=inline_query.query,
            prefix=FRIEND_CHALLENGE_INLINE_SHARE_PREFIX,
        )
        result = (
            await _build_friend_challenge_result(
                session=session,
                user_id=int(user.id),
                challenge_id=challenge_id,
            )
            if challenge_id is not None
            else None
        )
    await inline_query.answer(
        [result] if result is not None else [],
        cache_time=0,
        is_personal=True,
    )
