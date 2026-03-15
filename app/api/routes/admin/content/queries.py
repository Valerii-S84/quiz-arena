from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_questions import QuizQuestion
from app.db.models.quiz_sessions import QuizSession
from app.db.models.user_events import UserEvent


@dataclass(frozen=True)
class ContentHealthRows:
    totals: list[tuple[Any, Any]]
    attempts: list[tuple[Any, Any]]
    flagged: list[UserEvent]
    grammar_event: UserEvent | None
    duplicate_rows: list[tuple[str, Any]]
    mode_level_rows: list[tuple[Any, Any, Any]]


async def fetch_content_health_rows(session: AsyncSession) -> ContentHealthRows:
    totals = (
        await session.execute(
            select(QuizQuestion.level, func.count(QuizQuestion.question_id)).group_by(
                QuizQuestion.level
            )
        )
    ).all()

    attempts = (
        await session.execute(
            select(QuizQuestion.level, func.count(QuizAttempt.id))
            .join(QuizAttempt, QuizAttempt.question_id == QuizQuestion.question_id)
            .group_by(QuizQuestion.level)
        )
    ).all()

    flagged = (
        (
            await session.execute(
                select(UserEvent)
                .where(
                    UserEvent.event_type.in_(
                        ("question_flagged", "question_duplicate", "grammar_flagged")
                    )
                )
                .order_by(UserEvent.created_at.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )

    grammar_event = (
        await session.execute(
            select(UserEvent)
            .where(UserEvent.event_type == "grammar_pipeline_status")
            .order_by(UserEvent.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    duplicate_rows = (
        await session.execute(
            select(QuizQuestion.question_text, func.count(QuizQuestion.question_id))
            .group_by(QuizQuestion.question_text)
            .having(func.count(QuizQuestion.question_id) > 1)
            .order_by(func.count(QuizQuestion.question_id).desc())
            .limit(20)
        )
    ).all()

    mode_level_rows = (
        await session.execute(
            select(QuizSession.mode_code, QuizQuestion.level, func.count(QuizAttempt.id))
            .select_from(QuizAttempt)
            .join(QuizSession, QuizSession.id == QuizAttempt.session_id)
            .join(QuizQuestion, QuizQuestion.question_id == QuizAttempt.question_id)
            .group_by(QuizSession.mode_code, QuizQuestion.level)
        )
    ).all()

    return ContentHealthRows(
        totals=[(level, total) for level, total in totals],
        attempts=[(level, total) for level, total in attempts],
        flagged=list(flagged),
        grammar_event=grammar_event,
        duplicate_rows=[(text, count) for text, count in duplicate_rows],
        mode_level_rows=[
            (mode_code, level, attempts_total)
            for mode_code, level, attempts_total in mode_level_rows
        ],
    )
