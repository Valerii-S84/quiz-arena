from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from uuid import UUID

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_limit_keyboard,
    build_friend_challenge_share_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.offers import build_offer_keyboard
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.offers.constants import TRG_LOCKED_MODE_CLICK
from app.economy.offers.service import OfferLoggingError, OfferService
from app.game.modes.presentation import display_mode_label
from app.game.modes.rules import is_zero_cost_source
from app.game.sessions.errors import (
    DailyChallengeAlreadyPlayedError,
    EnergyInsufficientError,
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
    FriendChallengePaymentRequiredError,
    InvalidAnswerOptionError,
    ModeLockedError,
    SessionNotFoundError,
)
from app.game.sessions.service import GameSessionService
from app.game.sessions.types import FriendChallengeRoundStartResult, FriendChallengeSnapshot, StartSessionResult
from app.services.user_onboarding import UserOnboardingService

router = Router(name="gameplay")

ANSWER_RE = re.compile(r"^answer:([0-9a-f\-]{36}):([0-3])$")
FRIEND_NEXT_RE = re.compile(r"^friend:next:([0-9a-f\-]{36})$")


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


def _build_friend_finish_text(
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

    if challenge.winner_user_id is None:
        outcome_text = TEXTS_DE["msg.friend.challenge.finished.draw"]
    elif challenge.winner_user_id == user_id:
        outcome_text = TEXTS_DE["msg.friend.challenge.finished.win"]
    else:
        outcome_text = TEXTS_DE["msg.friend.challenge.finished.lose"].format(
            opponent_label=opponent_label
        )

    summary_text = TEXTS_DE["msg.friend.challenge.finished.summary"].format(
        my_score=my_score,
        opponent_score=opponent_score,
        opponent_label=opponent_label,
    )
    return "\n".join([outcome_text, summary_text])


def _friend_opponent_user_id(*, challenge: FriendChallengeSnapshot, user_id: int) -> int | None:
    if challenge.creator_user_id == user_id:
        return challenge.opponent_user_id
    if challenge.opponent_user_id == user_id:
        return challenge.creator_user_id
    return None


async def _resolve_opponent_label(*, challenge: FriendChallengeSnapshot, user_id: int) -> str:
    opponent_user_id = _friend_opponent_user_id(challenge=challenge, user_id=user_id)
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


async def _notify_opponent(
    callback: CallbackQuery,
    *,
    opponent_user_id: int | None,
    text: str,
    reply_markup=None,
) -> None:
    if opponent_user_id is None or callback.from_user is None:
        return

    async with SessionLocal.begin() as session:
        opponent = await UsersRepo.get_by_id(session, opponent_user_id)
    if opponent is None:
        return

    try:
        await callback.bot.send_message(
            chat_id=opponent.telegram_user_id,
            text=text,
            reply_markup=reply_markup,
        )
    except Exception:
        return


async def _build_friend_invite_link(callback: CallbackQuery, *, invite_token: str) -> str | None:
    try:
        me = await callback.bot.get_me()
    except Exception:
        return None
    if not me.username:
        return None
    return f"https://t.me/{me.username}?start=fc_{invite_token}"


async def _start_mode(
    callback: CallbackQuery,
    *,
    mode_code: str,
    source: str,
    idempotency_key: str,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)

    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

        try:
            result = await GameSessionService.start_session(
                session,
                user_id=snapshot.user_id,
                mode_code=mode_code,
                source=source,
                idempotency_key=idempotency_key,
                now_utc=now_utc,
            )
        except ModeLockedError:
            offer_selection = None
            try:
                offer_selection = await OfferService.evaluate_and_log_offer(
                    session,
                    user_id=snapshot.user_id,
                    idempotency_key=f"offer:locked:{callback.id}",
                    now_utc=now_utc,
                    trigger_event=TRG_LOCKED_MODE_CLICK,
                )
            except OfferLoggingError:
                offer_selection = None

            text = (
                TEXTS_DE[offer_selection.text_key]
                if offer_selection is not None
                else TEXTS_DE["msg.locked.mode"]
            )
            keyboard = (
                build_offer_keyboard(offer_selection)
                if offer_selection is not None
                else build_home_keyboard()
            )
            await callback.message.answer(text, reply_markup=keyboard)
            await callback.answer()
            return
        except EnergyInsufficientError:
            offer_selection = None
            try:
                offer_selection = await OfferService.evaluate_and_log_offer(
                    session,
                    user_id=snapshot.user_id,
                    idempotency_key=f"offer:energy:{callback.id}",
                    now_utc=now_utc,
                )
            except OfferLoggingError:
                offer_selection = None

            text = (
                TEXTS_DE[offer_selection.text_key]
                if offer_selection is not None
                else TEXTS_DE["msg.energy.empty.body"]
            )
            keyboard = (
                build_offer_keyboard(offer_selection)
                if offer_selection is not None
                else build_home_keyboard()
            )
            await callback.message.answer(text, reply_markup=keyboard)
            await callback.answer()
            return
        except DailyChallengeAlreadyPlayedError:
            await callback.message.answer(TEXTS_DE["msg.daily.challenge.used"], reply_markup=build_home_keyboard())
            await callback.answer()
            return

    question_text = _build_question_text(
        source=source,
        snapshot_free_energy=snapshot.free_energy,
        snapshot_paid_energy=snapshot.paid_energy,
        start_result=result,
    )

    await callback.message.answer(
        question_text,
        reply_markup=build_quiz_keyboard(
            session_id=str(result.session.session_id),
            options=result.session.options,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


async def _send_friend_round_question(
    callback: CallbackQuery,
    *,
    snapshot_free_energy: int,
    snapshot_paid_energy: int,
    round_start: FriendChallengeRoundStartResult,
) -> None:
    if callback.message is None or round_start.start_result is None:
        return

    question_text = _build_question_text(
        source="FRIEND_CHALLENGE",
        snapshot_free_energy=snapshot_free_energy,
        snapshot_paid_energy=snapshot_paid_energy,
        start_result=round_start.start_result,
    )
    await callback.message.answer(
        question_text,
        reply_markup=build_quiz_keyboard(
            session_id=str(round_start.start_result.session.session_id),
            options=round_start.start_result.session.options,
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "game:stop")
async def handle_game_stop(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(TEXTS_DE["msg.game.stopped"], reply_markup=build_home_keyboard())
    await callback.answer()


@router.callback_query(F.data == "play")
async def handle_play(callback: CallbackQuery) -> None:
    await _start_mode(
        callback,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        idempotency_key=f"start:play:{callback.id}",
    )


@router.callback_query(F.data == "daily_challenge")
async def handle_daily_challenge(callback: CallbackQuery) -> None:
    await _start_mode(
        callback,
        mode_code="DAILY_CHALLENGE",
        source="DAILY_CHALLENGE",
        idempotency_key=f"start:daily:{callback.id}",
    )


@router.callback_query(F.data.startswith("mode:"))
async def handle_mode(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    mode_code = callback.data.split(":", maxsplit=1)[1]
    await _start_mode(
        callback,
        mode_code=mode_code,
        source="MENU",
        idempotency_key=f"start:mode:{mode_code}:{callback.id}",
    )


@router.callback_query(F.data == "friend:challenge:create")
async def handle_friend_challenge_create(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        onboarding = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            challenge = await GameSessionService.create_friend_challenge(
                session,
                creator_user_id=onboarding.user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=now_utc,
            )
        except FriendChallengePaymentRequiredError:
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.limit.reached"],
                reply_markup=build_friend_challenge_limit_keyboard(),
            )
            await callback.answer()
            return

    invite_link = await _build_friend_invite_link(callback, invite_token=challenge.invite_token)
    body_lines = [
        TEXTS_DE["msg.friend.challenge.plan"],
        TEXTS_DE["msg.friend.challenge.created.short"],
    ]
    if invite_link is None:
        body_lines.insert(
            0,
            TEXTS_DE["msg.friend.challenge.created.fallback"].format(invite_token=challenge.invite_token),
        )
        await callback.message.answer(
            "\n".join(body_lines),
            reply_markup=build_friend_challenge_share_keyboard(
                invite_link=None,
                challenge_id=str(challenge.challenge_id),
            ),
        )
    else:
        body_lines.insert(
            0,
            TEXTS_DE["msg.friend.challenge.created"],
        )
        await callback.message.answer(
            "\n".join(body_lines),
            reply_markup=build_friend_challenge_share_keyboard(
                invite_link=invite_link,
                challenge_id=str(challenge.challenge_id),
            ),
        )
    await callback.answer()


@router.callback_query(F.data.regexp(FRIEND_NEXT_RE))
async def handle_friend_challenge_next(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    matched = FRIEND_NEXT_RE.match(callback.data)
    if matched is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    challenge_id = UUID(matched.group(1))
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            round_start = await GameSessionService.start_friend_challenge_round(
                session,
                user_id=snapshot.user_id,
                challenge_id=challenge_id,
                idempotency_key=f"start:friend:next:{challenge_id}:{callback.id}",
                now_utc=now_utc,
            )
        except (
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
            FriendChallengeCompletedError,
            FriendChallengeFullError,
        ):
            await callback.message.answer(TEXTS_DE["msg.friend.challenge.invalid"], reply_markup=build_home_keyboard())
            await callback.answer()
            return

    summary_lines = [
        _build_friend_score_text(
            challenge=round_start.snapshot,
            user_id=snapshot.user_id,
            opponent_label=await _resolve_opponent_label(
                challenge=round_start.snapshot,
                user_id=snapshot.user_id,
            ),
        ),
    ]
    if round_start.already_answered_current_round:
        summary_lines.append(
            TEXTS_DE["msg.friend.challenge.all_answered.waiting"].format(
                total_rounds=round_start.snapshot.total_rounds,
                opponent_label=await _resolve_opponent_label(
                    challenge=round_start.snapshot,
                    user_id=snapshot.user_id,
                ),
            )
        )
        await callback.message.answer(
            "\n".join(summary_lines),
            reply_markup=build_friend_challenge_back_keyboard(),
        )
        await callback.answer()
        return

    await _send_friend_round_question(
        callback,
        snapshot_free_energy=snapshot.free_energy,
        snapshot_paid_energy=snapshot.paid_energy,
        round_start=round_start,
    )
    await callback.answer()


@router.callback_query(F.data.regexp(ANSWER_RE))
async def handle_answer(callback: CallbackQuery) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    matched = ANSWER_RE.match(callback.data)
    if matched is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    session_id = UUID(matched.group(1))
    selected_option = int(matched.group(2))
    now_utc = datetime.now(timezone.utc)

    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

        try:
            result = await GameSessionService.submit_answer(
                session,
                user_id=snapshot.user_id,
                session_id=session_id,
                selected_option=selected_option,
                idempotency_key=f"answer:{callback.id}",
                now_utc=now_utc,
            )
        except SessionNotFoundError:
            await callback.message.answer(TEXTS_DE["msg.game.session.not_found"], reply_markup=build_home_keyboard())
            await callback.answer()
            return
        except InvalidAnswerOptionError:
            await callback.message.answer(TEXTS_DE["msg.system.error"])
            await callback.answer()
            return

    answer_key = "msg.game.answer.correct" if result.is_correct else "msg.game.answer.incorrect"
    response_lines = [TEXTS_DE[answer_key]]
    if result.selected_answer_text is not None:
        response_lines.append(
            TEXTS_DE["msg.game.answer.selected"].format(answer=result.selected_answer_text)
        )
    if result.correct_answer_text is not None:
        response_lines.append(
            TEXTS_DE["msg.game.answer.correct_label"].format(answer=result.correct_answer_text)
        )
    response_lines.append(
        TEXTS_DE["msg.game.streak"].format(
            current_streak=result.current_streak,
            best_streak=result.best_streak,
        )
    )
    await callback.message.answer("\n".join(response_lines))

    if result.mode_code is None or result.source is None:
        await callback.message.answer(TEXTS_DE["msg.game.stopped"], reply_markup=build_home_keyboard())
        await callback.answer()
        return

    if result.source == "DAILY_CHALLENGE":
        await callback.message.answer(TEXTS_DE["msg.game.daily.finished"], reply_markup=build_home_keyboard())
        await callback.answer()
        return

    if result.source == "FRIEND_CHALLENGE":
        if result.friend_challenge is None:
            await callback.message.answer(TEXTS_DE["msg.friend.challenge.invalid"], reply_markup=build_home_keyboard())
            await callback.answer()
            return

        challenge = result.friend_challenge
        opponent_label = await _resolve_opponent_label(
            challenge=challenge,
            user_id=snapshot.user_id,
        )
        await callback.message.answer(
            _build_friend_score_text(
                challenge=challenge,
                user_id=snapshot.user_id,
                opponent_label=opponent_label,
            )
        )

        opponent_user_id = _friend_opponent_user_id(challenge=challenge, user_id=snapshot.user_id)
        if result.friend_challenge_round_completed:
            round_result_text = TEXTS_DE["msg.friend.challenge.round.result"].format(
                round_no=(result.friend_challenge_answered_round or challenge.current_round)
            )
            await callback.message.answer(
                round_result_text,
            )
            if not result.idempotent_replay and opponent_user_id is not None:
                opponent_label_for_opponent = await _resolve_opponent_label(
                    challenge=challenge,
                    user_id=opponent_user_id,
                )
                await _notify_opponent(
                    callback,
                    opponent_user_id=opponent_user_id,
                    text="\n".join(
                        [
                            _build_friend_score_text(
                                challenge=challenge,
                                user_id=opponent_user_id,
                                opponent_label=opponent_label_for_opponent,
                            ),
                            round_result_text,
                        ]
                    ),
                )

        if challenge.status == "COMPLETED":
            my_finish_text = _build_friend_finish_text(
                challenge=challenge,
                user_id=snapshot.user_id,
                opponent_label=opponent_label,
            )
            await callback.message.answer(my_finish_text, reply_markup=build_home_keyboard())
            if not result.idempotent_replay and opponent_user_id is not None:
                opponent_label_for_opponent = await _resolve_opponent_label(
                    challenge=challenge,
                    user_id=opponent_user_id,
                )
                await _notify_opponent(
                    callback,
                    opponent_user_id=opponent_user_id,
                    text="\n".join(
                        [
                            _build_friend_score_text(
                                challenge=challenge,
                                user_id=opponent_user_id,
                                opponent_label=opponent_label_for_opponent,
                            ),
                            _build_friend_finish_text(
                                challenge=challenge,
                                user_id=opponent_user_id,
                                opponent_label=opponent_label_for_opponent,
                            ),
                        ]
                    ),
                    reply_markup=build_home_keyboard(),
                )
            await callback.answer()
            return

        async with SessionLocal.begin() as session:
            snapshot = await UserOnboardingService.ensure_home_snapshot(
                session,
                telegram_user=callback.from_user,
            )
            try:
                round_start = await GameSessionService.start_friend_challenge_round(
                    session,
                    user_id=snapshot.user_id,
                    challenge_id=challenge.challenge_id,
                    idempotency_key=f"start:friend:auto:{challenge.challenge_id}:{callback.id}",
                    now_utc=now_utc,
                )
            except (
                FriendChallengeNotFoundError,
                FriendChallengeAccessError,
                FriendChallengeCompletedError,
                FriendChallengeFullError,
            ):
                await callback.message.answer(TEXTS_DE["msg.friend.challenge.invalid"], reply_markup=build_home_keyboard())
                await callback.answer()
                return

        if round_start.start_result is not None:
            await _send_friend_round_question(
                callback,
                snapshot_free_energy=snapshot.free_energy,
                snapshot_paid_energy=snapshot.paid_energy,
                round_start=round_start,
            )
        else:
            waiting_text = TEXTS_DE["msg.friend.challenge.all_answered.waiting"].format(
                total_rounds=challenge.total_rounds,
                opponent_label=opponent_label,
            )
            await callback.message.answer(
                waiting_text,
                reply_markup=build_friend_challenge_back_keyboard(),
            )

        await callback.answer()
        return

    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

        try:
            next_result = await GameSessionService.start_session(
                session,
                user_id=snapshot.user_id,
                mode_code=result.mode_code,
                source=result.source,
                idempotency_key=f"start:auto:{result.mode_code}:{callback.id}",
                now_utc=now_utc,
                preferred_question_level=result.next_preferred_level,
            )
        except ModeLockedError:
            await callback.message.answer(TEXTS_DE["msg.locked.mode"], reply_markup=build_home_keyboard())
            await callback.answer()
            return
        except EnergyInsufficientError:
            offer_selection = None
            try:
                offer_selection = await OfferService.evaluate_and_log_offer(
                    session,
                    user_id=snapshot.user_id,
                    idempotency_key=f"offer:energy:auto:{callback.id}",
                    now_utc=now_utc,
                )
            except OfferLoggingError:
                offer_selection = None

            text = (
                TEXTS_DE[offer_selection.text_key]
                if offer_selection is not None
                else TEXTS_DE["msg.energy.empty.body"]
            )
            keyboard = (
                build_offer_keyboard(offer_selection)
                if offer_selection is not None
                else build_home_keyboard()
            )
            await callback.message.answer(text, reply_markup=keyboard)
            await callback.answer()
            return

    question_text = _build_question_text(
        source=result.source,
        snapshot_free_energy=snapshot.free_energy,
        snapshot_paid_energy=snapshot.paid_energy,
        start_result=next_result,
    )
    await callback.message.answer(
        question_text,
        reply_markup=build_quiz_keyboard(
            session_id=str(next_result.session.session_id),
            options=next_result.session.options,
        ),
        parse_mode="HTML",
    )
    await callback.answer()
