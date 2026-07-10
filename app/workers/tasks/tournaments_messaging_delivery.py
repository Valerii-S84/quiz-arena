from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.game.tournaments.constants import TOURNAMENT_STATUS_COMPLETED
from app.services.telegram_delivery import (
    TelegramDeliveryTarget,
    build_delivery_idempotency_key,
    mark_telegram_delivery_failed,
    mark_telegram_delivery_sent,
    prepare_telegram_delivery,
)
from app.workers.tasks.tournaments_messaging_context import TournamentRoundMessagingContext


@dataclass(frozen=True, slots=True)
class TournamentRoundDeliveryResult:
    sent: int
    edited: int
    failed: int
    skipped: int
    new_message_ids: dict[int, int]
    replaced_message_ids: dict[int, int]


async def deliver_round_messages(
    *,
    context: TournamentRoundMessagingContext,
    build_bot_fn: Callable[[], Any],
    resolve_match_context_fn: Callable[..., tuple[str | None, int | None]],
    build_standings_lines_fn: Callable[..., list[str]],
    build_completed_text_fn: Callable[..., str],
    build_round_text_fn: Callable[..., str],
    format_deadline_fn: Callable[..., str],
    build_keyboard_fn: Callable[..., object],
    add_share_button_fn: Callable[..., object],
    build_share_url_fn: Callable[..., str],
    is_message_not_modified_error_fn: Callable[[Exception], bool],
    logger: Any,
) -> TournamentRoundDeliveryResult:
    sent = 0
    edited = 0
    failed = 0
    skipped = 0
    new_message_ids: dict[int, int] = {}
    replaced_message_ids: dict[int, int] = {}
    happened_at = datetime.now(timezone.utc)
    flow = "private_tournament_round_messaging"
    task_name = "tournaments_messaging.run_private_tournament_round_messaging"
    correlation_id = str(context.parsed_tournament_id)

    bot = build_bot_fn()
    try:
        for user_id in context.standings_user_ids:
            chat_id = context.telegram_targets.get(user_id)
            existing_message_id = context.participant_rows[user_id].standings_message_id
            target = _private_round_delivery_target(
                flow=flow,
                task_name=task_name,
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                delivery_operation=_delivery_operation(existing_message_id),
            )
            delivery = await prepare_telegram_delivery(target=target, happened_at=happened_at)
            if not delivery.should_send:
                skipped += 1
                continue

            play_challenge_id, opponent_user_id = resolve_match_context_fn(
                round_matches=context.round_matches,
                viewer_user_id=user_id,
            )
            standings_lines = build_standings_lines_fn(
                standings_user_ids=context.standings_user_ids,
                labels=context.labels,
                points_by_user=context.points_by_user,
                viewer_user_id=user_id,
            )
            if context.tournament.status == TOURNAMENT_STATUS_COMPLETED:
                text = build_completed_text_fn(
                    tournament_name=context.tournament.name,
                    tournament_format=context.tournament.format,
                    place=context.place_by_user[user_id],
                    my_points=context.points_by_user.get(user_id, "0"),
                    standings_lines=standings_lines,
                )
            else:
                text = build_round_text_fn(
                    tournament_name=context.tournament.name,
                    tournament_format=context.tournament.format,
                    round_no=max(1, int(context.tournament.current_round)),
                    deadline_text=format_deadline_fn(context.tournament.round_deadline),
                    opponent_label=(
                        context.labels.get(opponent_user_id)
                        if opponent_user_id is not None
                        else None
                    ),
                    standings_lines=standings_lines,
                )
            keyboard = build_keyboard_fn(
                invite_code=context.tournament.invite_code,
                tournament_id=str(context.tournament.id),
                can_join=False,
                can_start=False,
                play_challenge_id=play_challenge_id,
                show_share_result=context.tournament.status == TOURNAMENT_STATUS_COMPLETED,
            )
            keyboard = add_share_button_fn(
                keyboard=keyboard,
                share_url=build_share_url_fn(
                    invite_code=context.tournament.invite_code,
                    tournament_name=context.tournament.name,
                ),
            )
            if existing_message_id is None:
                try:
                    message = await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=keyboard,
                    )
                except Exception as exc:
                    failed += 1
                    await mark_telegram_delivery_failed(
                        idempotency_key=target.idempotency_key,
                        happened_at=happened_at,
                        exc=exc,
                    )
                    continue
                await mark_telegram_delivery_sent(
                    idempotency_key=target.idempotency_key,
                    happened_at=happened_at,
                )
                sent += 1
                new_message_ids[user_id] = int(message.message_id)
                continue

            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=int(existing_message_id),
                    text=text,
                    reply_markup=keyboard,
                )
                await mark_telegram_delivery_sent(
                    idempotency_key=target.idempotency_key,
                    happened_at=happened_at,
                )
                edited += 1
            except Exception as exc:
                if is_message_not_modified_error_fn(exc):
                    await mark_telegram_delivery_sent(
                        idempotency_key=target.idempotency_key,
                        happened_at=happened_at,
                    )
                    edited += 1
                    continue
                try:
                    message = await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=keyboard,
                    )
                except Exception as send_exc:
                    failed += 1
                    await mark_telegram_delivery_failed(
                        idempotency_key=target.idempotency_key,
                        happened_at=happened_at,
                        exc=send_exc,
                    )
                    continue
                await mark_telegram_delivery_sent(
                    idempotency_key=target.idempotency_key,
                    happened_at=happened_at,
                )
                sent += 1
                replaced_message_ids[user_id] = int(message.message_id)
    except Exception as exc:
        logger.warning(
            "private_tournament_round_message_failed",
            tournament_id=str(context.parsed_tournament_id),
            error_type=type(exc).__name__,
        )
        failed += 1
    finally:
        await bot.session.close()

    return TournamentRoundDeliveryResult(
        sent=sent,
        edited=edited,
        failed=failed,
        skipped=skipped,
        new_message_ids=new_message_ids,
        replaced_message_ids=replaced_message_ids,
    )


def _private_round_delivery_target(
    *,
    flow: str,
    task_name: str,
    correlation_id: str,
    user_id: int,
    chat_id: int | None,
    delivery_operation: str,
) -> TelegramDeliveryTarget:
    target_id = f"{user_id}:{delivery_operation}"
    return TelegramDeliveryTarget(
        flow=flow,
        task_name=task_name,
        correlation_id=correlation_id,
        target_type="user",
        target_id=target_id,
        idempotency_key=build_delivery_idempotency_key(
            flow=flow,
            correlation_id=correlation_id,
            target_type="user",
            target_id=target_id,
        ),
        telegram_user_id=chat_id,
        chat_id=chat_id,
        safe_context={"tournament_id": correlation_id, "user_id": user_id},
    )


def _delivery_operation(existing_message_id: int | None) -> str:
    if existing_message_id is None:
        return "send"
    return f"edit:{int(existing_message_id)}"


__all__ = ["TournamentRoundDeliveryResult", "deliver_round_messages"]
