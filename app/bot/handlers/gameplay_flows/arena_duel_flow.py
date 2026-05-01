from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_views import _format_user_label
from app.bot.keyboards.duels import (
    ArenaDuelButton,
    build_arena_accept_keyboard,
    build_arena_empty_keyboard,
    build_arena_list_keyboard,
    build_arena_published_keyboard,
    build_arena_result_keyboard,
    build_duel_paywall_keyboard,
)
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.constants import ARENA_ATTEMPT_RESULT_DRAW, ARENA_ATTEMPT_RESULT_WIN
from app.game.arena_duels.errors import (
    ArenaDuelAccessError,
    ArenaDuelAlreadyAttemptedError,
    ArenaDuelExpiredError,
    ArenaDuelNotFoundError,
    ArenaDuelOwnAttemptError,
    ArenaDuelPaymentRequiredError,
)
from app.game.arena_duels.types import (
    ArenaActiveDuelSnapshot,
    ArenaAttemptCompletionResult,
    ArenaAttemptResultLine,
    ArenaBaselineStartResult,
    ArenaChallengerStartResult,
)
from app.game.questions.catalog import QUICK_MIX_MODE_CODE
from app.game.sessions.errors import FriendChallengeAccessError
from app.game.sessions.types import StartSessionResult

_ARENA_MARKERS = ("🔥", "👑", "⚡")


@dataclass(frozen=True, slots=True)
class _ArenaAcceptScreen:
    duel: ArenaActiveDuelSnapshot | None
    opponent_label: str = ""
    guard_text_key: str | None = None


async def handle_arena_open(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    list_active_arena_duels,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        active_duels = await list_active_arena_duels(session, now_utc=now_utc)
        items = await _build_arena_list_items(
            session=session,
            user_onboarding_service=user_onboarding_service,
            active_duels=active_duels,
        )

    if not items:
        await callback.message.answer(
            TEXTS_DE["msg.duels.arena.empty"],
            reply_markup=build_arena_empty_keyboard(),
        )
        await callback.answer()
        return

    await callback.message.answer(
        TEXTS_DE["msg.duels.arena.list"].format(duels=_format_arena_list(active_duels, items)),
        reply_markup=build_arena_list_keyboard(duels=items),
    )
    await callback.answer()


async def handle_arena_accept_preview(
    callback: CallbackQuery,
    *,
    arena_accept_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    get_arena_duel_accept_preview,
) -> None:
    duel_id = _parse_arena_duel_id(
        callback,
        pattern=arena_accept_re,
        parse_uuid_callback=parse_uuid_callback,
    )
    if duel_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        screen = await _load_arena_accept_screen(
            session=session,
            telegram_user=callback.from_user,
            user_onboarding_service=user_onboarding_service,
            get_arena_duel_accept_preview=get_arena_duel_accept_preview,
            duel_id=duel_id,
            now_utc=now_utc,
        )

    if screen.guard_text_key is not None:
        await _send_arena_guard(
            callback,
            text_key=screen.guard_text_key,
            reply_markup=build_arena_empty_keyboard(),
        )
        return
    if screen.duel is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    await callback.message.answer(
        TEXTS_DE["msg.duels.arena.accept"].format(
            opponent_label=screen.opponent_label,
            score_line=_format_score_line(
                score=screen.duel.score,
                time_ms=screen.duel.time_ms,
            ),
        ),
        reply_markup=build_arena_accept_keyboard(duel_id=str(screen.duel.duel_id)),
    )
    await callback.answer()


async def handle_arena_start_create(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    resolve_arena_create_access_type,
    create_arena_duel_baseline,
    build_question_text,
) -> None:
    await _start_arena_round(
        callback,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        resolve_access_type=resolve_arena_create_access_type,
        start_arena_round=lambda session, user_id, now_utc, access_type: create_arena_duel_baseline(
            session,
            creator_user_id=user_id,
            mode_code=QUICK_MIX_MODE_CODE,
            now_utc=now_utc,
            access_type=access_type,
        ),
        build_question_text=build_question_text,
    )


async def _load_arena_accept_screen(
    *,
    session,
    telegram_user,
    user_onboarding_service,
    get_arena_duel_accept_preview,
    duel_id: UUID,
    now_utc: datetime,
) -> _ArenaAcceptScreen:
    snapshot = await user_onboarding_service.ensure_home_snapshot(
        session,
        telegram_user=telegram_user,
    )
    try:
        duel = await get_arena_duel_accept_preview(
            session,
            duel_id=duel_id,
            user_id=snapshot.user_id,
            now_utc=now_utc,
        )
    except ArenaDuelOwnAttemptError:
        return _ArenaAcceptScreen(duel=None, guard_text_key="msg.duels.arena.own")
    except ArenaDuelAlreadyAttemptedError:
        return _ArenaAcceptScreen(
            duel=None,
            guard_text_key="msg.duels.arena.already_played",
        )
    except (ArenaDuelExpiredError, ArenaDuelNotFoundError, ArenaDuelAccessError):
        return _ArenaAcceptScreen(duel=None, guard_text_key="msg.duels.arena.expired")

    opponent_label = await _resolve_arena_user_label(
        session=session,
        user_onboarding_service=user_onboarding_service,
        user_id=duel.creator_user_id,
    )
    return _ArenaAcceptScreen(duel=duel, opponent_label=opponent_label)


async def handle_arena_start_attempt(
    callback: CallbackQuery,
    *,
    arena_start_attempt_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    resolve_arena_accept_access_type,
    accept_arena_duel,
    build_question_text,
) -> None:
    duel_id = _parse_arena_duel_id(
        callback,
        pattern=arena_start_attempt_re,
        parse_uuid_callback=parse_uuid_callback,
    )
    if duel_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await _start_arena_round(
        callback,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        resolve_access_type=resolve_arena_accept_access_type,
        start_arena_round=lambda session, user_id, now_utc, access_type: accept_arena_duel(
            session,
            duel_id=duel_id,
            user_id=user_id,
            now_utc=now_utc,
            access_type=access_type,
        ),
        build_question_text=build_question_text,
    )


async def send_arena_completion_result(
    callback: CallbackQuery,
    *,
    completion: ArenaAttemptCompletionResult,
    session_local,
    user_onboarding_service,
) -> None:
    if callback.message is None:
        return
    completed_attempt = getattr(completion, "completed_attempt", None)
    if completed_attempt is None:
        return

    opponent_attempt = getattr(completion, "opponent_attempt", None)
    if opponent_attempt is None:
        await callback.message.answer(
            TEXTS_DE["msg.duels.arena.published"].format(
                score_line=_format_score_line(
                    score=completed_attempt.score,
                    time_ms=completed_attempt.time_ms,
                )
            ),
            reply_markup=build_arena_published_keyboard(),
        )
        return

    async with session_local.begin() as session:
        opponent_label = await _resolve_arena_user_label(
            session=session,
            user_onboarding_service=user_onboarding_service,
            user_id=opponent_attempt.user_id,
        )
    text = _build_arena_result_text(
        completed_attempt=completed_attempt,
        opponent_attempt=opponent_attempt,
        opponent_label=opponent_label,
    )
    await callback.message.answer(
        text,
        reply_markup=build_arena_result_keyboard(
            user_won=completed_attempt.result == ARENA_ATTEMPT_RESULT_WIN
        ),
    )


async def _start_arena_round(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    resolve_access_type,
    start_arena_round: Callable[[object, int, datetime, str], Awaitable[object]],
    build_question_text,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    guard_text_key: str | None = None
    payment_required = False
    result: object | None = None
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            access_type = await resolve_access_type(
                session,
                user_id=snapshot.user_id,
                now_utc=now_utc,
            )
            result = await start_arena_round(session, snapshot.user_id, now_utc, access_type)
        except ArenaDuelPaymentRequiredError:
            payment_required = True
        except ArenaDuelOwnAttemptError:
            guard_text_key = "msg.duels.arena.own"
        except ArenaDuelAlreadyAttemptedError:
            guard_text_key = "msg.duels.arena.already_played"
        except (
            ArenaDuelExpiredError,
            ArenaDuelNotFoundError,
            ArenaDuelAccessError,
            FriendChallengeAccessError,
        ):
            guard_text_key = "msg.duels.arena.expired"

    if payment_required:
        await _send_duel_paywall(callback)
        return

    if guard_text_key is not None:
        await _send_arena_guard(
            callback,
            text_key=guard_text_key,
            reply_markup=build_arena_empty_keyboard(),
        )
        return

    start_result = _extract_start_result(result)
    if start_result is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    await callback.message.answer(
        build_question_text(
            source="ARENA_DUEL",
            snapshot_free_energy=snapshot.free_energy,
            snapshot_paid_energy=snapshot.paid_energy,
            start_result=start_result,
        ),
        reply_markup=build_quiz_keyboard(
            session_id=str(start_result.session.session_id),
            options=start_result.session.options,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


def _extract_start_result(result: object | None) -> StartSessionResult | None:
    if result is None:
        return None
    if isinstance(result, ArenaBaselineStartResult):
        return result.start_result
    if isinstance(result, ArenaChallengerStartResult):
        return result.start_result
    return getattr(result, "start_result", None)


async def _build_arena_list_items(
    *,
    session,
    user_onboarding_service,
    active_duels: Sequence[ArenaActiveDuelSnapshot],
) -> tuple[ArenaDuelButton, ...]:
    items: list[ArenaDuelButton] = []
    for index, duel in enumerate(active_duels):
        label = await _resolve_arena_user_label(
            session=session,
            user_onboarding_service=user_onboarding_service,
            user_id=duel.creator_user_id,
        )
        marker = _ARENA_MARKERS[index % len(_ARENA_MARKERS)]
        items.append(ArenaDuelButton(duel_id=str(duel.duel_id), label=label, marker=marker))
    return tuple(items)


def _format_arena_list(
    active_duels: Sequence[ArenaActiveDuelSnapshot],
    items: Sequence[ArenaDuelButton],
) -> str:
    lines: list[str] = []
    for duel, item in zip(active_duels, items, strict=True):
        lines.append(item.marker + " " + item.label)
        lines.append(_format_score_line(score=duel.score, time_ms=duel.time_ms))
        lines.append("")
    return "\n".join(lines).strip()


def _build_arena_result_text(
    *,
    completed_attempt: ArenaAttemptResultLine,
    opponent_attempt: ArenaAttemptResultLine,
    opponent_label: str,
) -> str:
    user_score_line = _format_score_line(
        score=completed_attempt.score,
        time_ms=completed_attempt.time_ms,
    )
    opponent_score_line = _format_score_line(
        score=opponent_attempt.score,
        time_ms=opponent_attempt.time_ms,
    )
    if completed_attempt.result == ARENA_ATTEMPT_RESULT_WIN:
        if completed_attempt.score == opponent_attempt.score:
            return TEXTS_DE["msg.duels.arena.result.win.time"].format(
                score=completed_attempt.score,
                user_score_line=user_score_line,
                opponent_label=opponent_label,
                opponent_score_line=opponent_score_line,
            )
        return TEXTS_DE["msg.duels.arena.result.win.score"].format(
            user_score_line=user_score_line,
            opponent_label=opponent_label,
            opponent_score_line=opponent_score_line,
        )
    if completed_attempt.result == ARENA_ATTEMPT_RESULT_DRAW:
        return TEXTS_DE["msg.duels.arena.result.draw"].format(
            score=completed_attempt.score,
            user_score_line=user_score_line,
            opponent_label=opponent_label,
            opponent_score_line=opponent_score_line,
        )
    if completed_attempt.score == opponent_attempt.score:
        return TEXTS_DE["msg.duels.arena.result.loss.time"].format(
            score=completed_attempt.score,
            user_score_line=user_score_line,
            opponent_label=opponent_label,
            opponent_score_line=opponent_score_line,
        )
    return TEXTS_DE["msg.duels.arena.result.loss.score"].format(
        user_score_line=user_score_line,
        opponent_label=opponent_label,
        opponent_score_line=opponent_score_line,
    )


async def _resolve_arena_user_label(*, session, user_onboarding_service, user_id: int) -> str:
    user = await user_onboarding_service.get_by_id(session, user_id)
    if user is None:
        return f"Spieler #{user_id}"
    return _format_user_label(
        username=user.username,
        first_name=user.first_name,
        fallback=f"Spieler #{user_id}",
    )


async def _send_arena_guard(callback: CallbackQuery, *, text_key: str, reply_markup) -> None:
    if callback.message is not None:
        await callback.message.answer(TEXTS_DE[text_key], reply_markup=reply_markup)
    await callback.answer()


async def _send_duel_paywall(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(
            TEXTS_DE["msg.duels.limit.reached"],
            reply_markup=build_duel_paywall_keyboard(),
        )
    await callback.answer()


def _parse_arena_duel_id(callback: CallbackQuery, *, pattern, parse_uuid_callback) -> UUID | None:
    if callback.data is None:
        return None
    return parse_uuid_callback(pattern=pattern, callback_data=callback.data)


def _format_score_line(*, score: int, time_ms: int) -> str:
    total_seconds = max(0, int(round(time_ms / 1000)))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{score}/7 · {minutes:02d}:{seconds:02d}"
