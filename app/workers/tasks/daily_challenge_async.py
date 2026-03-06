from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import structlog

from app.bot.application import build_bot
from app.bot.keyboards.daily import build_daily_push_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.repo.daily_push_logs_repo import DailyPushLogsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.energy.constants import BERLIN_TIMEZONE
from app.game.sessions.service.daily_question_sets import ensure_daily_question_set
from app.workers.tasks.daily_challenge_config import (
    DAILY_PUSH_BATCH_SIZE,
    DAILY_PUSH_KIND_EVENING_REMINDER,
    DAILY_PUSH_KIND_MORNING,
    VALID_DAILY_PUSH_KINDS,
)

logger = structlog.get_logger("app.workers.tasks.daily_challenge")


def _berlin_today(now_utc: datetime) -> date:
    return now_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()


def _resolve_push_kind(push_kind: str) -> str:
    candidate = str(push_kind).strip().upper()
    if candidate not in VALID_DAILY_PUSH_KINDS:
        raise ValueError(f"Unsupported daily push kind: {push_kind}")
    return candidate


def _build_push_text(*, push_kind: str, current_streak: int) -> str:
    lines = [
        TEXTS_DE["msg.daily.push.evening"]
        if push_kind == DAILY_PUSH_KIND_EVENING_REMINDER
        else TEXTS_DE["msg.daily.push.base"]
    ]
    if current_streak > 0:
        lines.append(TEXTS_DE["msg.daily.push.streak"].format(streak=current_streak))
    return "\n".join(lines)


async def run_daily_question_set_precompute_async() -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    berlin_date = _berlin_today(now_utc)

    async with SessionLocal.begin() as session:
        question_ids = await ensure_daily_question_set(session, berlin_date=berlin_date)

    result: dict[str, object] = {
        "generated_at": now_utc.isoformat(),
        "berlin_date": berlin_date.isoformat(),
        "questions_total": len(question_ids),
    }
    logger.info("daily_question_set_precomputed", **result)
    return result


async def run_daily_push_notifications_async(
    *,
    batch_size: int = DAILY_PUSH_BATCH_SIZE,
    push_kind: str = DAILY_PUSH_KIND_MORNING,
) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    berlin_date = _berlin_today(now_utc)
    resolved_batch_size = max(1, int(batch_size))
    resolved_push_kind = _resolve_push_kind(push_kind)

    scanned_total = 0
    sent_total = 0
    skipped_total = 0
    last_user_id: int | None = None

    bot = build_bot()
    try:
        while True:
            async with SessionLocal.begin() as session:
                targets = await UsersRepo.list_daily_push_targets(
                    session,
                    berlin_date=berlin_date,
                    push_kind=resolved_push_kind,
                    after_user_id=last_user_id,
                    limit=resolved_batch_size,
                )
            if not targets:
                break

            for user_id, telegram_user_id, current_streak in targets:
                last_user_id = user_id
                scanned_total += 1
                async with SessionLocal.begin() as session:
                    created = await DailyPushLogsRepo.create_once(
                        session,
                        user_id=user_id,
                        berlin_date=berlin_date,
                        push_kind=resolved_push_kind,
                        push_sent_at=now_utc,
                    )
                if not created:
                    skipped_total += 1
                    continue
                text = _build_push_text(
                    push_kind=resolved_push_kind,
                    current_streak=current_streak,
                )
                try:
                    await bot.send_message(
                        chat_id=telegram_user_id,
                        text=text,
                        reply_markup=build_daily_push_keyboard(),
                    )
                    sent_total += 1
                except Exception:
                    skipped_total += 1
    finally:
        await bot.session.close()

    result: dict[str, object] = {
        "generated_at": now_utc.isoformat(),
        "berlin_date": berlin_date.isoformat(),
        "batch_size": resolved_batch_size,
        "push_kind": resolved_push_kind,
        "users_scanned_total": scanned_total,
        "sent_total": sent_total,
        "skipped_total": skipped_total,
    }
    logger.info("daily_push_notifications_processed", **result)
    return result
