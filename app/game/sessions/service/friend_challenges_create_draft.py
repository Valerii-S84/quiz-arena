from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(slots=True)
class FriendChallengeCreationDraft:
    challenge_id: UUID
    creator_user_id: int
    opponent_user_id: int | None
    challenge_type: str
    mode_code: str
    access_type: str
    total_rounds: int
    question_ids: list[str]
    status: str
    series_id: UUID | None = None
    series_game_number: int = 1
    series_best_of: int = 1
