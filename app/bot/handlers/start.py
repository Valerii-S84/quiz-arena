from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.friend_challenge import build_friend_challenge_back_keyboard
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.offers import build_offer_keyboard
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.keyboards.shop import build_shop_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.offers.service import OfferLoggingError, OfferService
from app.game.modes.presentation import display_mode_label
from app.game.modes.rules import is_zero_cost_source
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.service import GameSessionService
from app.game.sessions.types import FriendChallengeSnapshot, StartSessionResult
from app.services.user_onboarding import UserOnboardingService

router = Router(name="start")
START_PAYLOAD_RE = re.compile(r"^/start(?:@\w+)?(?:\s+(.+))?$")
START_FRIEND_PAYLOAD_RE = re.compile(r"^fc_([a-f0-9]{32})$", re.IGNORECASE)


def _format_user_label(*, username: str | None, first_name: str | None, fallback: str = "Freund") -> str:
    if username:
        normalized = username.strip()
        if normalized:
            return f"@{normalized}"
    if first_name:
        normalized_name = first_name.strip()
        if normalized_name:
            return normalized_name
    return fallback


def _extract_start_payload(text: str | None) -> str | None:
    if not text:
        return None
    matched = START_PAYLOAD_RE.match(text.strip())
    if matched is None:
        return None
    payload = matched.group(1)
    return payload.strip() if payload else None


def _extract_friend_challenge_token(start_payload: str | None) -> str | None:
    if not start_payload:
        return None
    matched = START_FRIEND_PAYLOAD_RE.fullmatch(start_payload.strip())
    if matched is None:
        return None
    return matched.group(1).lower()


def _build_home_text(*, free_energy: int, paid_energy: int, current_streak: int) -> str:
    return "\n".join(
        [
            TEXTS_DE["msg.home.title"],
            TEXTS_DE["msg.home.energy"].format(
                free_energy=free_energy,
                paid_energy=paid_energy,
            ),
            TEXTS_DE["msg.home.streak"].format(streak=current_streak),
            TEXTS_DE["msg.home.hint"],
        ]
    )


def _build_question_text(
    *,
    source: str,
    snapshot_free_energy: int,
    snapshot_paid_energy: int,
    start_result: StartSessionResult,
) -> str:
    mode_line = TEXTS_DE["msg.game.mode"].format(
        mode_code=display_mode_label(start_result.session.mode_code)
    )
    energy_line = TEXTS_DE["msg.game.energy.left"].format(
        free_energy=(
            snapshot_free_energy if is_zero_cost_source(source) else start_result.energy_free
        ),
        paid_energy=(
            snapshot_paid_energy if is_zero_cost_source(source) else start_result.energy_paid
        ),
    )
    return "\n".join(
        [
            f"<b>{html.escape(mode_line)}</b>",
            html.escape(energy_line),
            "",
            "<b>Frage:</b>",
            f"<b>{html.escape(start_result.session.text)}</b>",
            "",
            html.escape(TEXTS_DE["msg.game.choose_option"]),
        ]
    )


def _build_friend_score_text(
    *,
    challenge: FriendChallengeSnapshot,
    user_id: int,
    opponent_label: str,
) -> str:
    if challenge.creator_user_id == user_id:
        my_score = challenge.creator_score
        opponent_score = challenge.opponent_score
    else:
        my_score = challenge.opponent_score
        opponent_score = challenge.creator_score
    round_now = challenge.current_round
    if challenge.status == "COMPLETED":
        round_now = challenge.total_rounds
    return TEXTS_DE["msg.friend.challenge.score"].format(
        my_score=my_score,
        opponent_score=opponent_score,
        opponent_label=opponent_label,
        round_now=round_now,
        total_rounds=challenge.total_rounds,
    )


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
    try:
        await message.bot.send_message(
            chat_id=creator.telegram_user_id,
            text=TEXTS_DE["msg.friend.challenge.opponent.joined"].format(
                opponent_label=joiner_label
            ),
        )
    except Exception:
        return


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    if message.from_user is None:
        await message.answer(TEXTS_DE["msg.system.error"])
        return

    now_utc = datetime.now(timezone.utc)
    offer_selection = None
    start_payload = _extract_start_payload(message.text)
    friend_invite_token = _extract_friend_challenge_token(start_payload)
    challenge_start = None
    challenge_joined_now = False
    challenge_error_key: str | None = None
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=message.from_user,
            start_payload=start_payload,
        )
        if friend_invite_token is not None:
            try:
                join_result = await GameSessionService.join_friend_challenge_by_token(
                    session,
                    user_id=snapshot.user_id,
                    invite_token=friend_invite_token,
                    now_utc=now_utc,
                )
                challenge = join_result.snapshot
                challenge_joined_now = join_result.joined_now
                challenge_start = await GameSessionService.start_friend_challenge_round(
                    session,
                    user_id=snapshot.user_id,
                    challenge_id=challenge.challenge_id,
                    idempotency_key=f"start:friend:join:{challenge.challenge_id}:{message.message_id}",
                    now_utc=now_utc,
                )
            except (
                FriendChallengeNotFoundError,
                FriendChallengeCompletedError,
                FriendChallengeAccessError,
            ):
                challenge_error_key = "msg.friend.challenge.invalid"
            except FriendChallengeFullError:
                challenge_error_key = "msg.friend.challenge.full"
        else:
            try:
                offer_selection = await OfferService.evaluate_and_log_offer(
                    session,
                    user_id=snapshot.user_id,
                    idempotency_key=f"offer:start:{message.from_user.id}:{message.message_id}",
                    now_utc=now_utc,
                )
            except OfferLoggingError:
                offer_selection = None

    if friend_invite_token is not None:
        if challenge_error_key is not None or challenge_start is None:
            await message.answer(TEXTS_DE[challenge_error_key or "msg.friend.challenge.invalid"], reply_markup=build_home_keyboard())
            return

        if challenge_joined_now:
            await _notify_creator_about_join(
                message,
                challenge=challenge_start.snapshot,
                joiner_user_id=snapshot.user_id,
            )

        opponent_label = await _resolve_opponent_label(
            challenge=challenge_start.snapshot,
            user_id=snapshot.user_id,
        )
        summary_lines = [
            TEXTS_DE["msg.friend.challenge.joined"],
            TEXTS_DE["msg.friend.challenge.with"].format(opponent_label=opponent_label),
            TEXTS_DE["msg.friend.challenge.plan"],
            TEXTS_DE["msg.friend.challenge.play.instant"],
            _build_friend_score_text(
                challenge=challenge_start.snapshot,
                user_id=snapshot.user_id,
                opponent_label=opponent_label,
            ),
        ]
        if challenge_start.waiting_for_opponent:
            summary_lines.append(TEXTS_DE["msg.friend.challenge.waiting"])
        if challenge_start.already_answered_current_round:
            summary_lines.append(TEXTS_DE["msg.friend.challenge.round.already.answered"])
        await message.answer(
            "\n".join(summary_lines),
            reply_markup=build_friend_challenge_back_keyboard(),
        )
        if challenge_start.start_result is not None:
            question_text = _build_question_text(
                source="FRIEND_CHALLENGE",
                snapshot_free_energy=snapshot.free_energy,
                snapshot_paid_energy=snapshot.paid_energy,
                start_result=challenge_start.start_result,
            )
            await message.answer(
                question_text,
                reply_markup=build_quiz_keyboard(
                    session_id=str(challenge_start.start_result.session.session_id),
                    options=challenge_start.start_result.session.options,
                ),
                parse_mode="HTML",
            )
        return

    response_text = _build_home_text(
        free_energy=snapshot.free_energy,
        paid_energy=snapshot.paid_energy,
        current_streak=snapshot.current_streak,
    )
    await message.answer(response_text, reply_markup=build_home_keyboard())
    if offer_selection is not None:
        await message.answer(
            TEXTS_DE[offer_selection.text_key],
            reply_markup=build_offer_keyboard(offer_selection),
        )


@router.callback_query(F.data == "shop:open")
async def handle_shop_open(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(TEXTS_DE["msg.shop.title"], reply_markup=build_shop_keyboard())
    await callback.answer()


@router.callback_query(F.data == "home:open")
async def handle_home_open(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

    response_text = _build_home_text(
        free_energy=snapshot.free_energy,
        paid_energy=snapshot.paid_energy,
        current_streak=snapshot.current_streak,
    )
    await callback.message.answer(response_text, reply_markup=build_home_keyboard())
    await callback.answer()
