from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class WalkoverNotification:
    tournament_id: UUID
    round_no: int
    user_a: int
    user_b: int
    user_a_points: int
    user_b_points: int
    rounds_total: int
    tournament_registration_deadline: datetime
    next_round_start_time: datetime | None


@dataclass(slots=True)
class DailyCupRoundsAdvanceOutcome:
    rounds_started_total: int = 0
    tournaments_completed_total: int = 0
    matches_settled_total: int = 0
    matches_created_total: int = 0
    completed_ids: list[str] = field(default_factory=list)
    walkover_notifications: list[WalkoverNotification] = field(default_factory=list)
    events: list[dict[str, object]] = field(default_factory=list)


def match_scores_from_challenge(*, match: Any, challenge: Any) -> tuple[int, int]:
    creator_user_id = int(challenge.creator_user_id)
    creator_score = int(challenge.creator_score)
    opponent_score = int(challenge.opponent_score)
    if int(match.user_a) == creator_user_id:
        return creator_score, opponent_score
    return opponent_score, creator_score


async def advance_due_daily_cup_rounds(
    *,
    session: Any,
    now_utc_value: datetime,
    tournaments_repo: Any,
    participants_repo: Any,
    matches_repo: Any,
    challenges_repo: Any,
    settle_round_and_advance_fn: Any,
    tournament_type_daily_arena: str,
    pending_match_status: str,
    walkover_match_status: str,
    tournament_completed_status: str,
    max_rounds_fn: Any,
) -> DailyCupRoundsAdvanceOutcome:
    outcome = DailyCupRoundsAdvanceOutcome()
    due_rounds = await tournaments_repo.list_due_round_deadline_for_update(
        session,
        now_utc=now_utc_value,
        limit=50,
        tournament_type=tournament_type_daily_arena,
    )
    for tournament in due_rounds:
        was_completed = tournament.status == tournament_completed_status
        round_before = max(1, int(tournament.current_round))
        participants_total = await participants_repo.count_for_tournament(
            session,
            tournament_id=tournament.id,
        )
        rounds_total = max_rounds_fn(participants_total=participants_total)
        pending_round_matches = await matches_repo.list_by_tournament_round_for_update(
            session,
            tournament_id=tournament.id,
            round_no=round_before,
        )
        pending_match_ids = {
            match.id for match in pending_round_matches if match.status == pending_match_status
        }
        transition = await settle_round_and_advance_fn(
            session,
            tournament=tournament,
            now_utc=now_utc_value,
        )
        settled_count = int(transition["matches_settled"])
        started_count = int(transition["round_started"])
        completed_count = int(transition["tournament_completed"])
        outcome.matches_settled_total += settled_count
        outcome.matches_created_total += int(transition["matches_created"])
        outcome.rounds_started_total += started_count
        outcome.tournaments_completed_total += completed_count

        for _ in range(settled_count):
            outcome.events.append(
                {
                    "event_type": "daily_cup_match_completed",
                    "payload": {"tournament_id": str(tournament.id), "round_no": round_before},
                }
            )
        if started_count > 0:
            outcome.events.append(
                {
                    "event_type": "daily_cup_round_started",
                    "payload": {
                        "tournament_id": str(tournament.id),
                        "round_no": int(tournament.current_round),
                    },
                }
            )
        if completed_count > 0 or (
            tournament.status == tournament_completed_status and not was_completed
        ):
            outcome.completed_ids.append(str(tournament.id))
        if settled_count == 0 or not pending_match_ids:
            continue

        settled_round_matches = await matches_repo.list_by_tournament_round_for_update(
            session,
            tournament_id=tournament.id,
            round_no=round_before,
        )
        for match in settled_round_matches:
            if (
                match.id not in pending_match_ids
                or match.status != walkover_match_status
                or match.user_b is None
                or match.winner_id is None
                or match.friend_challenge_id is None
            ):
                continue
            challenge = await challenges_repo.get_by_id(session, match.friend_challenge_id)
            if challenge is None:
                continue
            user_a_points, user_b_points = match_scores_from_challenge(
                match=match,
                challenge=challenge,
            )
            outcome.walkover_notifications.append(
                WalkoverNotification(
                    tournament_id=match.tournament_id,
                    round_no=int(match.round_no),
                    user_a=int(match.user_a),
                    user_b=int(match.user_b),
                    user_a_points=user_a_points,
                    user_b_points=user_b_points,
                    rounds_total=rounds_total,
                    tournament_registration_deadline=tournament.registration_deadline,
                    next_round_start_time=(
                        tournament.round_start_time
                        if int(tournament.current_round) == int(match.round_no) + 1
                        else None
                    ),
                )
            )
    return outcome


__all__ = [
    "DailyCupRoundsAdvanceOutcome",
    "WalkoverNotification",
    "advance_due_daily_cup_rounds",
    "match_scores_from_challenge",
]
