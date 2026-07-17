from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.workers.tasks.tournaments_message_delivery_persistence import (
    persist_private_tournament_sent_message,
    prepare_private_tournament_delivery,
    record_private_tournament_delivery_failure,
    record_private_tournament_delivery_skipped,
)
from app.workers.tasks.tournaments_messaging_context import TournamentRoundMessagingContext
from app.workers.tasks.tournaments_messaging_delivery_content import build_round_message_payload
from app.workers.tasks.tournaments_messaging_delivery_runtime import (
    deliver_round_messages_with_dependencies,
)
from app.workers.tasks.tournaments_messaging_delivery_targets import (
    delivery_operation,
    fallback_delivery_operation,
    private_round_content_version,
    private_round_delivery_content_key,
    private_round_delivery_target,
)
from app.workers.tasks.tournaments_messaging_delivery_types import (
    TournamentRoundDeliveryFailureResult,
    TournamentRoundDeliveryOperations,
    TournamentRoundDeliveryRequest,
    TournamentRoundDeliveryResult,
)


async def _prepare_round_delivery(*args: Any, **kwargs: Any) -> Any:
    return await prepare_private_tournament_delivery(*args, **kwargs)


async def _record_round_delivery_failure(
    *args: Any, **kwargs: Any
) -> TournamentRoundDeliveryFailureResult:
    return await record_private_tournament_delivery_failure(*args, **kwargs)


async def _record_round_delivery_skipped(*args: Any, **kwargs: Any) -> None:
    await record_private_tournament_delivery_skipped(*args, **kwargs)


async def _persist_initial_round_message(*args: Any, **kwargs: Any) -> int:
    return await persist_private_tournament_sent_message(*args, **kwargs)


async def _persist_edited_round_message(*args: Any, **kwargs: Any) -> int:
    return await persist_private_tournament_sent_message(*args, **kwargs)


async def _persist_replacement_round_message(*args: Any, **kwargs: Any) -> int:
    return await persist_private_tournament_sent_message(*args, **kwargs)


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
    request = TournamentRoundDeliveryRequest(
        context=context,
        build_bot_fn=build_bot_fn,
        resolve_match_context_fn=resolve_match_context_fn,
        build_standings_lines_fn=build_standings_lines_fn,
        build_completed_text_fn=build_completed_text_fn,
        build_round_text_fn=build_round_text_fn,
        format_deadline_fn=format_deadline_fn,
        build_keyboard_fn=build_keyboard_fn,
        add_share_button_fn=add_share_button_fn,
        build_share_url_fn=build_share_url_fn,
        is_message_not_modified_error_fn=is_message_not_modified_error_fn,
        logger=logger,
    )
    operations = TournamentRoundDeliveryOperations(
        prepare_delivery=_prepare_round_delivery,
        record_delivery_failure=_record_round_delivery_failure,
        record_delivery_skipped=_record_round_delivery_skipped,
        persist_initial_message=_persist_initial_round_message,
        persist_edited_message=_persist_edited_round_message,
        persist_replacement_message=_persist_replacement_round_message,
        build_target=private_round_delivery_target,
        delivery_operation=delivery_operation,
        fallback_delivery_operation=fallback_delivery_operation,
        content_version=private_round_content_version,
        content_key=private_round_delivery_content_key,
        build_payload=build_round_message_payload,
    )
    return await deliver_round_messages_with_dependencies(
        request=request,
        operations=operations,
    )


__all__ = ["TournamentRoundDeliveryResult", "deliver_round_messages"]
