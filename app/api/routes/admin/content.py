from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from app.api.routes.admin.audit import write_admin_audit
from app.api.routes.admin.deps import AdminPrincipal, add_admin_noindex_header, get_current_admin
from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_questions import QuizQuestion
from app.db.models.user_events import UserEvent
from app.db.session import SessionLocal

router = APIRouter(prefix="/admin/content", tags=["admin-content"])


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

    return {
        "level_stats": level_stats,
        "flagged_questions": flagged_items,
        "grammar_pipeline": grammar_status,
        "duplicates": [
            {"question_text": text, "count": int(count)} for text, count in duplicate_rows
        ],
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
