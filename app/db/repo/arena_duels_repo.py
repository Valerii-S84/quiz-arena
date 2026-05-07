from __future__ import annotations

from .arena_duels_repo_accept import ArenaDuelsRepoAcceptMixin
from .arena_duels_repo_attempts import ArenaDuelsRepoAttemptsMixin
from .arena_duels_repo_listing import ArenaDuelsRepoListingMixin
from .arena_duels_repo_models import (
    ArenaActiveDuelRow,
    ArenaAttemptCompletionSummary,
    ArenaAttemptDuelContext,
    ArenaDuelAcceptContext,
)
from .arena_duels_repo_writes import ArenaDuelsRepoWritesMixin


class ArenaDuelsRepo(
    ArenaDuelsRepoWritesMixin,
    ArenaDuelsRepoAcceptMixin,
    ArenaDuelsRepoAttemptsMixin,
    ArenaDuelsRepoListingMixin,
):
    pass


__all__ = [
    "ArenaActiveDuelRow",
    "ArenaAttemptCompletionSummary",
    "ArenaAttemptDuelContext",
    "ArenaDuelAcceptContext",
    "ArenaDuelsRepo",
]
