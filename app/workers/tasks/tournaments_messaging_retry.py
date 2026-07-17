from __future__ import annotations

from typing import NotRequired, TypedDict


class PrivateRoundMessagingResult(TypedDict):
    processed: int
    participants_total: int
    sent: int
    edited: int
    failed: int
    skipped: int
    retry_count: NotRequired[int]
    retry_after_seconds: NotRequired[int | None]


class PrivateTournamentDeliveryRetryNeeded(RuntimeError):
    def __init__(self, *, retry_count: int, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            "private tournament delivery retry needed"
            f"; retry_count={retry_count}; retry_after_seconds={retry_after_seconds}"
        )


def raise_for_private_delivery_retry_needed(result: PrivateRoundMessagingResult) -> None:
    retry_count = int(result.get("retry_count") or 0)
    if retry_count <= 0:
        return
    raise PrivateTournamentDeliveryRetryNeeded(
        retry_count=retry_count,
        retry_after_seconds=max(1, int(result.get("retry_after_seconds") or 1)),
    )


__all__ = [
    "PrivateRoundMessagingResult",
    "PrivateTournamentDeliveryRetryNeeded",
    "raise_for_private_delivery_retry_needed",
]
