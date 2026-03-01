from __future__ import annotations

from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.repo.tournament_matches_repo import TournamentMatchesRepo


def build_tournament_post_match_text(
    *,
    challenge,
    user_id: int,
    opponent_label: str,
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


def enqueue_tournament_post_match_updates(*, tournament_id: str) -> None:
    from app.bot.handlers import gameplay_tournament_notifications
    from app.workers.tasks.daily_cup_proof_cards import enqueue_daily_cup_proof_cards
    from app.workers.tasks.tournaments_proof_cards import enqueue_private_tournament_proof_cards

    gameplay_tournament_notifications.enqueue_tournament_round_messaging(
        tournament_id=tournament_id
    )
    enqueue_private_tournament_proof_cards(tournament_id=tournament_id)
    enqueue_daily_cup_proof_cards(tournament_id=tournament_id)
