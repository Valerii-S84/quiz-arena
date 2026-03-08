from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.application import build_bot
from app.bot.texts.de import TEXTS_DE
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.users_repo import UsersRepo
from app.game.tournaments.daily_cup_standings import calculate_daily_cup_standings
from app.workers.tasks.tournaments_messaging_text import format_points

_BERLIN_TZ = ZoneInfo("Europe/Berlin")


def _result_key(*, my_points: int, opponent_points: int, final_round: bool) -> str:
    if my_points > opponent_points:
        return (
            "msg.daily_cup.match_result_win_final"
            if final_round
            else "msg.daily_cup.match_result_win"
        )
    if my_points < opponent_points:
        return (
            "msg.daily_cup.match_result_loss_final"
            if final_round
            else "msg.daily_cup.match_result_loss"
        )
    return (
        "msg.daily_cup.match_result_draw_final"
        if final_round
        else "msg.daily_cup.match_result_draw"
    )


def _format_next_round_time(*, next_round_deadline: datetime | None) -> str:
    if next_round_deadline is None:
        return "-"
    return next_round_deadline.astimezone(_BERLIN_TZ).strftime("%H:%M")


def _build_result_text(
    *,
    round_no: int,
    rounds_total: int,
    my_points: int,
    opponent_points: int,
    place: int,
    total_players: int,
    total_score: str,
    next_round_deadline: datetime | None,
) -> str:
    rounds_left = max(0, rounds_total - round_no)
    is_final_round = rounds_left == 0
    next_round_no = min(rounds_total, round_no + 1)
    return TEXTS_DE[
        _result_key(
            my_points=my_points,
            opponent_points=opponent_points,
            final_round=is_final_round,
        )
    ].format(
        round_no=round_no,
        my_points=my_points,
        opponent_points=opponent_points,
        place=place,
        total=total_players,
        score=total_score,
        rounds_left=rounds_left,
        next_round_no=next_round_no,
        next_round_time=_format_next_round_time(next_round_deadline=next_round_deadline),
    )


async def send_daily_cup_match_result_messages(
    session: AsyncSession,
    *,
    tournament_id: UUID,
    round_no: int,
    user_a: int,
    user_b: int,
    user_a_points: int,
    user_b_points: int,
    rounds_total: int,
    next_round_deadline: datetime | None,
) -> None:
    try:
        standings = await calculate_daily_cup_standings(session, tournament_id=tournament_id)
    except AttributeError:
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=tournament_id,
        )
        standings = []
        for place, participant in enumerate(participants, start=1):
            standings.append(
                type(
                    "_Standing",
                    (),
                    {
                        "user_id": int(participant.user_id),
                        "place": place,
                        "participant": participant,
                    },
                )()
            )
    place_by_user = {item.user_id: item.place for item in standings}
    score_by_user = {item.user_id: format_points(item.participant.score) for item in standings}
    users = await UsersRepo.list_by_ids(session, [user_a, user_b])
    telegram_by_user = {int(item.id): int(item.telegram_user_id) for item in users}
    total_players = len(standings)

    notifications = (
        (user_a, user_a_points, user_b_points),
        (user_b, user_b_points, user_a_points),
    )
    bot = build_bot()
    try:
        for viewer_user_id, my_points, opponent_points in notifications:
            chat_id = telegram_by_user.get(viewer_user_id)
            place_value = place_by_user.get(viewer_user_id)
            if chat_id is None or place_value is None:
                continue
            text = _build_result_text(
                round_no=round_no,
                rounds_total=rounds_total,
                my_points=my_points,
                opponent_points=opponent_points,
                place=place_value,
                total_players=total_players,
                total_score=score_by_user.get(viewer_user_id, "0"),
                next_round_deadline=next_round_deadline,
            )
            try:
                await bot.send_message(chat_id=chat_id, text=text)
            except TelegramForbiddenError:
                continue
            except Exception:
                continue
    finally:
        await bot.session.close()


__all__ = ["send_daily_cup_match_result_messages"]
