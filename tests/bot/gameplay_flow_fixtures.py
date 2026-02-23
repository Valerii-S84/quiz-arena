from __future__ import annotations

from uuid import UUID

from app.game.sessions.types import FriendChallengeSnapshot, SessionQuestionView, StartSessionResult


def _challenge_snapshot(
    *, status: str = "ACTIVE", winner_user_id: int | None = None
) -> FriendChallengeSnapshot:
    return FriendChallengeSnapshot(
        challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        invite_token="token",
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        status=status,
        creator_user_id=10,
        opponent_user_id=20,
        current_round=3,
        total_rounds=12,
        creator_score=5,
        opponent_score=4,
        winner_user_id=winner_user_id,
    )


def _start_result() -> StartSessionResult:
    return StartSessionResult(
        session=SessionQuestionView(
            session_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            question_id="q-1",
            text="Frage?",
            options=("A", "B", "C", "D"),
            mode_code="QUICK_MIX_A1A2",
            source="MENU",
            category="Artikel - Nominativ",
            question_number=3,
            total_questions=12,
        ),
        energy_free=18,
        energy_paid=2,
        idempotent_replay=False,
    )
