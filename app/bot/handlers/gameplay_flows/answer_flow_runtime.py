from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows import answer_flow_delivery
from app.bot.handlers.gameplay_flows.answer_flow_runtime_context import (
    AnswerFlowDeps,
    ParsedAnswerPayload,
    PostGamePromptState,
    SubmittedAnswerPayload,
    parse_answer_payload,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import InvalidAnswerOptionError, SessionNotFoundError


async def _reserve_post_game_prompt(
    *,
    session,
    snapshot,
    result,
    now_utc: datetime,
    deps: AnswerFlowDeps,
) -> PostGamePromptState:
    if result.source not in {"MENU", "DAILY_CHALLENGE"}:
        return PostGamePromptState()

    show_channel_bonus_prompt = await deps.channel_bonus_service.should_show_post_game_prompt(
        session,
        user_id=snapshot.user_id,
        idempotent_replay=result.idempotent_replay,
    )
    if show_channel_bonus_prompt:
        await deps.emit_analytics_event(
            session,
            event_type="channel_bonus_shown",
            source=deps.event_source_bot,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload={"source": "post_game"},
        )
        return PostGamePromptState(show_channel_bonus_prompt=True)

    show_referral_prompt = await deps.referral_service.reserve_post_game_prompt(
        session,
        user_id=snapshot.user_id,
        now_utc=now_utc,
    )
    if show_referral_prompt:
        await deps.emit_analytics_event(
            session,
            event_type="referral_prompt_shown",
            source=deps.event_source_bot,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload={"entrypoint": "post_game"},
        )
    return PostGamePromptState(show_referral_prompt=show_referral_prompt)


async def _submit_answer(
    callback: CallbackQuery,
    *,
    parsed_answer: ParsedAnswerPayload,
    deps: AnswerFlowDeps,
) -> SubmittedAnswerPayload | None:
    now_utc = datetime.now(timezone.utc)

    async with deps.session_local.begin() as session:
        snapshot = await deps.user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=parsed_answer.telegram_user,
        )

        try:
            result = await deps.game_session_service.submit_answer(
                session,
                user_id=snapshot.user_id,
                session_id=parsed_answer.session_id,
                selected_option=parsed_answer.selected_option,
                idempotency_key=f"answer:{callback.id}",
                now_utc=now_utc,
            )
        except SessionNotFoundError:
            await parsed_answer.message.answer(
                TEXTS_DE["msg.game.session.not_found"],
                reply_markup=build_home_keyboard(),
            )
            await callback.answer()
            return None
        except InvalidAnswerOptionError:
            await parsed_answer.message.answer(TEXTS_DE["msg.system.error"])
            await callback.answer()
            return None

        post_game_prompt = await _reserve_post_game_prompt(
            session=session,
            snapshot=snapshot,
            result=result,
            now_utc=now_utc,
            deps=deps,
        )

    return SubmittedAnswerPayload(
        now_utc=now_utc,
        snapshot=snapshot,
        result=result,
        post_game_prompt=post_game_prompt,
    )


async def run_answer_flow(
    callback: CallbackQuery,
    *,
    parse_answer_callback,
    deps: AnswerFlowDeps,
    send_home_message,
) -> None:
    parsed_answer = await parse_answer_payload(
        callback,
        parse_answer_callback=parse_answer_callback,
    )
    if parsed_answer is None:
        return

    submitted_answer = await _submit_answer(
        callback,
        parsed_answer=parsed_answer,
        deps=deps,
    )
    if submitted_answer is None:
        return

    await answer_flow_delivery.dispatch_submitted_answer(
        callback,
        message=parsed_answer.message,
        submitted_answer=submitted_answer,
        deps=deps,
        send_home_message=send_home_message,
    )
