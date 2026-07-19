from __future__ import annotations

from datetime import datetime, timezone

from app.game.arena_duels.analytics import (
    ARENA_EVENT_DUEL_PAYWALL_SHOWN,
    ArenaPaywallContext,
    build_arena_event_payload,
    with_paywall_context,
)
from app.game.arena_duels.types import ArenaAttemptCompletionResult, ArenaAttemptResultLine


async def emit_duel_paywall_shown(
    *,
    session_local,
    completion: ArenaAttemptCompletionResult,
    completed_attempt: ArenaAttemptResultLine,
    action: str,
    paywall_context: ArenaPaywallContext,
    emit_arena_analytics_event,
) -> None:
    async with session_local.begin() as session:
        await emit_arena_analytics_event(
            session,
            event_type=ARENA_EVENT_DUEL_PAYWALL_SHOWN,
            happened_at=datetime.now(timezone.utc),
            user_id=completed_attempt.user_id,
            payload=with_paywall_context(
                build_arena_event_payload(
                    user_id=completed_attempt.user_id,
                    arena_duel_id=completion.duel.duel_id,
                    action=action,
                    result=completed_attempt.result,
                    score=completed_attempt.score,
                    time_ms=completed_attempt.time_ms,
                ),
                paywall_context=paywall_context,
            ),
        )
