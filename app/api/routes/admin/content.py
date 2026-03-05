from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from app.api.routes.admin.audit import write_admin_audit
from app.api.routes.admin.deps import AdminPrincipal, add_admin_noindex_header, get_current_admin
from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_questions import QuizQuestion
from app.db.models.quiz_sessions import QuizSession
from app.db.models.user_events import UserEvent
from app.db.session import SessionLocal

router = APIRouter(prefix="/admin/content", tags=["admin-content"])
LEVEL_SORT_ORDER: dict[str, int] = {
    "A1": 1,
    "A2": 2,
    "B1": 3,
    "B2": 4,
    "C1": 5,
    "C2": 6,
}


def _level_sort_key(level: str) -> tuple[int, str]:
    normalized = level.upper()
    return (LEVEL_SORT_ORDER.get(normalized, 99), normalized)


@router.get("")
async def get_content_health(
    response: Response,
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)

    async with SessionLocal.begin() as session:
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
        attempt_map = {str(level): int(total) for level, total in attempts}

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

    level_stats = []
    for level, total in totals:
        total_count = int(total)
        answered = attempt_map.get(str(level), 0)
        coverage = round((answered / total_count) * 100, 2) if total_count > 0 else 0
        level_stats.append(
            {
                "level": str(level),
                "total_questions": total_count,
                "attempts": answered,
                "coverage_percent": coverage,
            }
        )

    flagged_items = [
        {
            "id": int(item.id),
            "user_id": int(item.user_id),
            "reason": item.event_type,
            "payload": item.payload,
            "created_at": item.created_at.isoformat(),
        }
        for item in flagged
    ]

    grammar_status: dict[str, object] = {
        "status": "unknown",
        "updated_at": None,
        "payload": {},
    }
    if grammar_event is not None:
        grammar_status = {
            "status": str(grammar_event.payload.get("status") or "unknown"),
            "updated_at": grammar_event.created_at.isoformat(),
            "payload": grammar_event.payload,
        }

    mode_totals: dict[str, int] = {}
    total_mode_attempts = 0
    for mode_code, _, attempts_total in mode_level_rows:
        attempts_count = int(attempts_total)
        mode_key = str(mode_code)
        mode_totals[mode_key] = mode_totals.get(mode_key, 0) + attempts_count
        total_mode_attempts += attempts_count

    mode_level_distribution = []
    sorted_mode_level_rows = sorted(
        mode_level_rows,
        key=lambda row: (str(row[0]), _level_sort_key(str(row[1]))),
    )
    for mode_code, level, attempts_total in sorted_mode_level_rows:
        mode_key = str(mode_code)
        level_key = str(level)
        attempts_count = int(attempts_total)
        mode_total = mode_totals.get(mode_key, 0)
        percent_in_mode = round((attempts_count / mode_total) * 100, 2) if mode_total > 0 else 0
        percent_of_all_attempts = (
            round((attempts_count / total_mode_attempts) * 100, 2) if total_mode_attempts > 0 else 0
        )
        mode_level_distribution.append(
            {
                "mode_code": mode_key,
                "level": level_key,
                "attempts": attempts_count,
                "percent_in_mode": percent_in_mode,
                "percent_of_all_attempts": percent_of_all_attempts,
            }
        )

    return {
        "level_stats": level_stats,
        "flagged_questions": flagged_items,
        "grammar_pipeline": grammar_status,
        "duplicates": [
            {"question_text": text, "count": int(count)} for text, count in duplicate_rows
        ],
        "mode_level_distribution": mode_level_distribution,
    }


@router.post("/flagged/{event_id}/approve")
async def approve_flagged_question(
    event_id: int,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        event = await session.get(UserEvent, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail={"code": "E_FLAG_NOT_FOUND"})
        event.payload = {**event.payload, "review": "approved", "reviewed_at": now_utc.isoformat()}
        await write_admin_audit(
            session,
            admin_email=admin.email,
            action="content_flag_approve",
            target_type="user_event",
            target_id=str(event_id),
            payload={},
            ip=admin.client_ip,
        )
    return {"ok": True, "id": event_id, "review": "approved"}


@router.post("/flagged/{event_id}/reject")
async def reject_flagged_question(
    event_id: int,
    response: Response,
    reason: str = Query(default="not_reproducible"),
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        event = await session.get(UserEvent, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail={"code": "E_FLAG_NOT_FOUND"})
        event.payload = {
            **event.payload,
            "review": "rejected",
            "reason": reason,
            "reviewed_at": now_utc.isoformat(),
        }
        await write_admin_audit(
            session,
            admin_email=admin.email,
            action="content_flag_reject",
            target_type="user_event",
            target_id=str(event_id),
            payload={"reason": reason},
            ip=admin.client_ip,
        )
    return {"ok": True, "id": event_id, "review": "rejected", "reason": reason}
