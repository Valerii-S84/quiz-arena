from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import Message

from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.core.config import get_settings
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.session import SessionLocal
from app.game.sessions.service.constants import DUEL_MAX_PUSH_PER_USER
from app.game.sessions.types import FriendChallengeSnapshot
from app.services.user_onboarding import UserOnboardingService


def _resolve_welcome_image_file_id(*, current_settings) -> str:
    resolved_file_id = getattr(current_settings, "resolved_welcome_image_file_id", "")
    if isinstance(resolved_file_id, str) and resolved_file_id.strip():
        return resolved_file_id.strip()
    welcome_image_file_id = getattr(current_settings, "welcome_image_file_id", "")
    home_header_file_id = getattr(current_settings, "telegram_home_header_file_id", "")
    return str(welcome_image_file_id).strip() or str(home_header_file_id).strip()


async def _send_home_message(
    message: Message,
    *,
    text: str,
    home_header_file_id: str | None = None,
) -> None:
    resolved_home_header_file_id = home_header_file_id
    if resolved_home_header_file_id is None:
        resolved_home_header_file_id = _resolve_welcome_image_file_id(
            current_settings=get_settings()
        )
    if not resolved_home_header_file_id:
        await message.answer(text, reply_markup=build_home_keyboard())
        return
    try:
        await message.answer_photo(
            photo=resolved_home_header_file_id,
            caption=text,
            reply_markup=build_home_keyboard(),
        )
    except Exception:
        await message.answer(text, reply_markup=build_home_keyboard())


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
        opponent = await UserOnboardingService.get_by_id(session, opponent_user_id)

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
        challenge_row = await FriendChallengesRepo.get_by_id_for_update(
            session, challenge.challenge_id
        )
        if challenge_row is None:
            return
        if challenge_row.creator_push_count >= DUEL_MAX_PUSH_PER_USER:
            return
        challenge_row.creator_push_count += 1
        challenge_row.updated_at = datetime.now(timezone.utc)
        creator = await UserOnboardingService.get_by_id(session, challenge.creator_user_id)

    if creator is None:
        return

    bot = message.bot
    if bot is None:
        return
    try:
        await bot.send_message(
            chat_id=creator.telegram_user_id,
            text=TEXTS_DE["msg.friend.challenge.opponent.ready"],
        )
    except Exception:
        return
