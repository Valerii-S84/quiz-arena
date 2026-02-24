from __future__ import annotations

from aiogram.types import Message

from app.bot.texts.de import TEXTS_DE
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.sessions.types import FriendChallengeSnapshot


def _format_user_label(
    *, username: str | None, first_name: str | None, fallback: str = "Freund"
) -> str:
    if username:
        normalized = username.strip()
        if normalized:
            return f"@{normalized}"
    if first_name:
        normalized_name = first_name.strip()
        if normalized_name:
            return normalized_name
    return fallback


async def _resolve_opponent_label(*, challenge: FriendChallengeSnapshot, user_id: int) -> str:
    if challenge.creator_user_id == user_id:
        opponent_user_id = challenge.opponent_user_id
    elif challenge.opponent_user_id == user_id:
        opponent_user_id = challenge.creator_user_id
    else:
        opponent_user_id = challenge.opponent_user_id

    if opponent_user_id is None:
        return "Freund"

    async with SessionLocal.begin() as session:
        opponent = await UsersRepo.get_by_id(session, opponent_user_id)

    if opponent is None:
        return "Freund"
    return _format_user_label(
        username=opponent.username,
        first_name=opponent.first_name,
        fallback="Freund",
    )


async def _notify_creator_about_join(
    message: Message,
    *,
    challenge: FriendChallengeSnapshot,
    joiner_user_id: int,
) -> None:
    if challenge.creator_user_id == joiner_user_id:
        return

    async with SessionLocal.begin() as session:
        creator = await UsersRepo.get_by_id(session, challenge.creator_user_id)
        joiner = await UsersRepo.get_by_id(session, joiner_user_id)

    if creator is None or joiner is None:
        return

    joiner_label = _format_user_label(
        username=joiner.username,
        first_name=joiner.first_name,
        fallback="Freund",
    )
    bot = message.bot
    if bot is None:
        return
    try:
        await bot.send_message(
            chat_id=creator.telegram_user_id,
            text=TEXTS_DE["msg.friend.challenge.opponent.joined"].format(
                opponent_label=joiner_label
            ),
        )
    except Exception:
        return
