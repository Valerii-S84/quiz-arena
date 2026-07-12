from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.services.telegram_delivery import (
    mark_telegram_delivery_failed,
    mark_telegram_delivery_sent,
    prepare_telegram_delivery,
)
from app.workers.tasks.messaging_fallback_delivery import (
    mark_original_edit_failed_after_fallback_failure,
    record_original_edit_skipped_after_fallback_skip,
    record_original_edit_skipped_after_fallback_success,
)
from app.workers.tasks.tournaments_messaging_context import TournamentRoundMessagingContext
from app.workers.tasks.tournaments_messaging_delivery_content import build_round_message_payload
from app.workers.tasks.tournaments_messaging_delivery_targets import (
    delivery_operation,
    fallback_delivery_operation,
    private_round_content_version,
    private_round_delivery_target,
)


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
    content_version = private_round_content_version(tournament=context.tournament)

    bot = build_bot_fn()
    try:
        for user_id in context.standings_user_ids:
            chat_id = context.telegram_targets.get(user_id)
            existing_message_id = context.participant_rows[user_id].standings_message_id
            target = private_round_delivery_target(
                flow=flow,
                task_name=task_name,
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                delivery_operation=delivery_operation(existing_message_id),
                content_version=content_version,
                tournament_status=str(context.tournament.status),
                current_round=int(context.tournament.current_round),
                pending_replay_safe=existing_message_id is not None,
            )
            delivery = await prepare_telegram_delivery(target=target, happened_at=happened_at)
            if not delivery.should_send:
                skipped += 1
                continue

            text, keyboard = build_round_message_payload(
                context=context,
                user_id=user_id,
                resolve_match_context_fn=resolve_match_context_fn,
                build_standings_lines_fn=build_standings_lines_fn,
                build_completed_text_fn=build_completed_text_fn,
                build_round_text_fn=build_round_text_fn,
                format_deadline_fn=format_deadline_fn,
                build_keyboard_fn=build_keyboard_fn,
                add_share_button_fn=add_share_button_fn,
                build_share_url_fn=build_share_url_fn,
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
                fallback_target = private_round_delivery_target(
                    flow=flow,
                    task_name=task_name,
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    delivery_operation=fallback_delivery_operation(existing_message_id),
                    content_version=content_version,
                    tournament_status=str(context.tournament.status),
                    current_round=int(context.tournament.current_round),
                    pending_replay_safe=False,
                )
                fallback_delivery = await prepare_telegram_delivery(
                    target=fallback_target,
                    happened_at=happened_at,
                )
                if not fallback_delivery.should_send:
                    skipped += 1
                    await record_original_edit_skipped_after_fallback_skip(
                        target=target,
                        happened_at=happened_at,
                        fallback_status=fallback_delivery.status,
                    )
                    continue
                try:
                    message = await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=keyboard,
                    )
                except Exception as send_exc:
                    failed += 1
                    failure = await mark_telegram_delivery_failed(
                        idempotency_key=fallback_target.idempotency_key,
                        happened_at=happened_at,
                        exc=send_exc,
                    )
                    await mark_original_edit_failed_after_fallback_failure(
                        idempotency_key=target.idempotency_key,
                        happened_at=happened_at,
                        failure=failure,
                    )
                    continue
                await mark_telegram_delivery_sent(
                    idempotency_key=fallback_target.idempotency_key,
                    happened_at=happened_at,
                )
                await record_original_edit_skipped_after_fallback_success(
                    target=target,
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


__all__ = ["TournamentRoundDeliveryResult", "deliver_round_messages"]
