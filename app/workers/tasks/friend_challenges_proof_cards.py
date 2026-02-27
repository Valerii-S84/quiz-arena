from __future__ import annotations

from uuid import UUID

import structlog
from aiogram.types import BufferedInputFile

from app.bot.application import build_bot
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.friend_challenges_proof_card_render import render_duel_proof_card_png

logger = structlog.get_logger("app.workers.tasks.friend_challenges_proof_cards")

_DUEL_FINAL_STATUSES = frozenset({"COMPLETED", "EXPIRED", "WALKOVER"})


def _is_celery_task(task_obj: object) -> bool:
    return type(task_obj).__module__.startswith("celery.")


def _resolve_user_label(*, user, fallback: str) -> str:
    if user is None:
        return fallback
    if user.username:
        return f"@{str(user.username).strip()}"
    if user.first_name:
        return str(user.first_name).strip() or fallback
    return fallback


def _build_caption(
    *,
    challenge_id: str,
    status: str,
    role: str,
    creator_score: int,
    opponent_score: int,
) -> str:
    if role == "creator":
        my_score = creator_score
        other_score = opponent_score
    else:
        my_score = opponent_score
        other_score = creator_score
    if status == "WALKOVER":
        prefix = "⌛ DUELL WALKOVER"
    elif status == "EXPIRED":
        prefix = "⌛ DUELL ABGELAUFEN"
    else:
        prefix = "🏆 DUELL ERGEBNIS"
    return (
        f"{prefix}\n"
        f"Score: Du {my_score} : Gegner {other_score}\n"
        f"ID: {challenge_id}"
    )


async def run_friend_challenge_proof_cards_async(*, challenge_id: str) -> dict[str, int]:
    try:
        parsed_challenge_id = UUID(challenge_id)
    except ValueError:
        return {"processed": 0, "sent": 0, "cached_reused": 0}

    async with SessionLocal.begin() as session:
        challenge = await FriendChallengesRepo.get_by_id_for_update(session, parsed_challenge_id)
        if challenge is None or challenge.status not in _DUEL_FINAL_STATUSES:
            return {"processed": 0, "sent": 0, "cached_reused": 0}

        creator = await UsersRepo.get_by_id(session, challenge.creator_user_id)
        opponent = (
            await UsersRepo.get_by_id(session, int(challenge.opponent_user_id))
            if challenge.opponent_user_id is not None
            else None
        )

        status = str(challenge.status)
        creator_score = int(challenge.creator_score)
        opponent_score = int(challenge.opponent_score)
        total_rounds = int(challenge.total_rounds)
        completed_at = challenge.completed_at
        creator_file_id = challenge.creator_proof_card_file_id
        opponent_file_id = challenge.opponent_proof_card_file_id
        creator_chat = int(creator.telegram_user_id) if creator is not None else None
        opponent_chat = int(opponent.telegram_user_id) if opponent is not None else None
        creator_name = _resolve_user_label(user=creator, fallback="Spieler 1")
        opponent_name = _resolve_user_label(user=opponent, fallback="Spieler 2")

    must_render = (
        (creator_chat is not None and not creator_file_id)
        or (opponent_chat is not None and not opponent_file_id)
    )
    card_png = (
        render_duel_proof_card_png(
            creator_name=creator_name,
            opponent_name=opponent_name,
            creator_score=creator_score,
            opponent_score=opponent_score,
            total_rounds=total_rounds,
            completed_at=completed_at,
        )
        if must_render
        else None
    )

    bot = build_bot()
    sent = 0
    cached_reused = 0
    new_creator_file_id: str | None = None
    new_opponent_file_id: str | None = None
    try:
        if creator_chat is not None:
            creator_caption = _build_caption(
                challenge_id=challenge_id,
                status=status,
                role="creator",
                creator_score=creator_score,
                opponent_score=opponent_score,
            )
            if creator_file_id:
                await bot.send_photo(
                    chat_id=creator_chat,
                    photo=creator_file_id,
                    caption=creator_caption,
                )
                sent += 1
                cached_reused += 1
            elif card_png is not None:
                creator_message = await bot.send_photo(
                    chat_id=creator_chat,
                    photo=BufferedInputFile(
                        card_png,
                        filename=f"duel_{challenge_id}_creator.png",
                    ),
                    caption=creator_caption,
                )
                sent += 1
                if creator_message.photo:
                    new_creator_file_id = creator_message.photo[-1].file_id

        if opponent_chat is not None:
            opponent_caption = _build_caption(
                challenge_id=challenge_id,
                status=status,
                role="opponent",
                creator_score=creator_score,
                opponent_score=opponent_score,
            )
            if opponent_file_id:
                await bot.send_photo(
                    chat_id=opponent_chat,
                    photo=opponent_file_id,
                    caption=opponent_caption,
                )
                sent += 1
                cached_reused += 1
            elif card_png is not None:
                opponent_message = await bot.send_photo(
                    chat_id=opponent_chat,
                    photo=BufferedInputFile(
                        card_png,
                        filename=f"duel_{challenge_id}_opponent.png",
                    ),
                    caption=opponent_caption,
                )
                sent += 1
                if opponent_message.photo:
                    new_opponent_file_id = opponent_message.photo[-1].file_id
    except Exception as exc:
        logger.warning(
            "friend_challenge_proof_card_send_failed",
            challenge_id=challenge_id,
            error_type=type(exc).__name__,
        )
    finally:
        await bot.session.close()

    if new_creator_file_id is not None or new_opponent_file_id is not None:
        async with SessionLocal.begin() as session:
            challenge_row = await FriendChallengesRepo.get_by_id_for_update(
                session,
                parsed_challenge_id,
            )
            if challenge_row is not None:
                if new_creator_file_id is not None and not challenge_row.creator_proof_card_file_id:
                    challenge_row.creator_proof_card_file_id = new_creator_file_id
                if new_opponent_file_id is not None and not challenge_row.opponent_proof_card_file_id:
                    challenge_row.opponent_proof_card_file_id = new_opponent_file_id

    return {"processed": 1, "sent": sent, "cached_reused": cached_reused}


def enqueue_friend_challenge_proof_cards(*, challenge_id: str) -> None:
    try:
        if _is_celery_task(run_friend_challenge_proof_cards):
            run_friend_challenge_proof_cards.delay(challenge_id=challenge_id)
        else:
            run_async_job(run_friend_challenge_proof_cards_async(challenge_id=challenge_id))
    except Exception as exc:
        logger.warning(
            "friend_challenge_proof_card_enqueue_failed",
            challenge_id=challenge_id,
            error_type=type(exc).__name__,
        )


@celery_app.task(name="app.workers.tasks.friend_challenges_proof_cards.run_friend_challenge_proof_cards")
def run_friend_challenge_proof_cards(*, challenge_id: str) -> dict[str, int]:
    return run_async_job(run_friend_challenge_proof_cards_async(challenge_id=challenge_id))
