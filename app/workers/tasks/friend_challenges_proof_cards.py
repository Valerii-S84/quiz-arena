from __future__ import annotations

from uuid import UUID

import structlog

from app.bot.application import build_bot
from app.bot.keyboards.friend_challenge import build_friend_challenge_result_share_keyboard
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.friend_challenges_proof_card_render import render_duel_proof_card_png
from app.workers.tasks.friend_challenges_proof_card_text import build_caption, resolve_user_label
from app.workers.tasks.friend_challenges_proof_cards_context import (
    load_friend_challenge_proof_cards_context,
)
from app.workers.tasks.friend_challenges_proof_cards_delivery import (
    deliver_friend_challenge_proof_cards,
)
from app.workers.tasks.friend_challenges_proof_cards_persistence import (
    persist_friend_challenge_proof_card_file_ids,
)

logger = structlog.get_logger("app.workers.tasks.friend_challenges_proof_cards")
_DUEL_FINAL_STATUSES = frozenset({"COMPLETED", "EXPIRED", "WALKOVER"})


def _is_celery_task(task_obj: object) -> bool:
    return type(task_obj).__module__.startswith("celery.")


async def run_friend_challenge_proof_cards_async(
    *,
    challenge_id: str,
    user_id: int | None = None,
) -> dict[str, int]:
    try:
        parsed_challenge_id = UUID(challenge_id)
    except ValueError:
        return {"processed": 0, "sent": 0, "cached_reused": 0}

    async with SessionLocal.begin() as session:
        context = await load_friend_challenge_proof_cards_context(
            session=session,
            parsed_challenge_id=parsed_challenge_id,
            requested_user_id=user_id,
            challenges_repo=FriendChallengesRepo,
            users_repo=UsersRepo,
            final_statuses=_DUEL_FINAL_STATUSES,
            resolve_user_label_fn=resolve_user_label,
        )
    if context is None:
        return {"processed": 0, "sent": 0, "cached_reused": 0}
    if not context.recipients:
        return {"processed": 1, "sent": 0, "cached_reused": 0}

    delivery = await deliver_friend_challenge_proof_cards(
        context=context,
        build_bot_fn=build_bot,
        build_keyboard_fn=build_friend_challenge_result_share_keyboard,
        build_caption_fn=build_caption,
        render_card_fn=render_duel_proof_card_png,
        logger=logger,
    )

    if delivery.new_creator_file_id is not None or delivery.new_opponent_file_id is not None:
        async with SessionLocal.begin() as session:
            await persist_friend_challenge_proof_card_file_ids(
                session=session,
                parsed_challenge_id=context.parsed_challenge_id,
                challenges_repo=FriendChallengesRepo,
                new_creator_file_id=delivery.new_creator_file_id,
                new_opponent_file_id=delivery.new_opponent_file_id,
            )

    return {
        "processed": 1,
        "sent": delivery.sent,
        "cached_reused": delivery.cached_reused,
    }


def enqueue_friend_challenge_proof_cards(
    *,
    challenge_id: str,
    user_id: int | None = None,
) -> None:
    try:
        if _is_celery_task(run_friend_challenge_proof_cards):
            run_friend_challenge_proof_cards.delay(
                challenge_id=challenge_id,
                user_id=user_id,
            )
        else:
            run_async_job(
                run_friend_challenge_proof_cards_async(
                    challenge_id=challenge_id,
                    user_id=user_id,
                )
            )
    except Exception as exc:
        logger.warning(
            "friend_challenge_proof_card_enqueue_failed",
            challenge_id=challenge_id,
            error_type=type(exc).__name__,
        )


@celery_app.task(
    name="app.workers.tasks.friend_challenges_proof_cards.run_friend_challenge_proof_cards"
)
def run_friend_challenge_proof_cards(
    *,
    challenge_id: str,
    user_id: int | None = None,
) -> dict[str, int]:
    return run_async_job(
        run_friend_challenge_proof_cards_async(
            challenge_id=challenge_id,
            user_id=user_id,
        )
    )
