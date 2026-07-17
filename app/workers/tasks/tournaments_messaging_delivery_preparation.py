from __future__ import annotations

from app.workers.tasks.tournaments_message_delivery_persistence import (
    PrivateTournamentStandingsFence,
)
from app.workers.tasks.tournaments_messaging_delivery_types import (
    TournamentRoundDeliveryContext,
    TournamentRoundDeliveryState,
    TournamentRoundMessageAttempt,
)


def persistence_fence(
    delivery_context: TournamentRoundDeliveryContext,
    attempt: TournamentRoundMessageAttempt,
) -> PrivateTournamentStandingsFence:
    tournament = delivery_context.request.context.tournament
    return PrivateTournamentStandingsFence(
        tournament_id=delivery_context.request.context.parsed_tournament_id,
        user_id=attempt.user_id,
        expected_message_id=attempt.existing_message_id,
        expected_status=str(tournament.status),
        expected_round=int(tournament.current_round),
    )


async def prepare_delivery(
    *,
    delivery_context: TournamentRoundDeliveryContext,
    state: TournamentRoundDeliveryState,
    attempt: TournamentRoundMessageAttempt,
) -> bool:
    preparation = await delivery_context.operations.prepare_delivery(attempt.target)
    if preparation.should_send:
        return True
    if getattr(preparation, "status", None) == "RETRY":
        state.record_retry(getattr(preparation, "retry_after_seconds", None))
        return False
    state.skipped += 1
    return False


__all__ = ["persistence_fence", "prepare_delivery"]
