from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.streak.time import berlin_local_date
from app.game.sessions import service as sessions_service_module
from app.game.sessions.service import GameSessionService

EXPECTED_START_LEVEL = "A1"
CANARY_MODES: tuple[str, ...] = ("ARTIKEL_SPRINT", "QUICK_MIX_A1A2")
REQUIRED_PROGRESS_COLUMNS: tuple[str, ...] = ("mix_step", "correct_in_mix")


def _expected_alembic_head() -> str:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    head = script.get_current_head()
    if head is None:
        raise RuntimeError("Unable to resolve Alembic expected head")
    return head


async def _current_alembic_version() -> str:
    async with SessionLocal() as session:
        current = (
            await session.execute(
                text(
                    """
                    SELECT version_num
                    FROM alembic_version
                    LIMIT 1
                    """
                )
            )
        ).scalar_one_or_none()
    if current is None:
        raise RuntimeError("alembic_version table is empty")
    return str(current)


async def _assert_progress_schema(session: AsyncSession) -> None:
    rows = (
        await session.execute(
            text(
                """
                SELECT column_name, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'mode_progress'
                  AND column_name IN (:c1, :c2)
                ORDER BY column_name
                """
            ),
            {
                "c1": REQUIRED_PROGRESS_COLUMNS[0],
                "c2": REQUIRED_PROGRESS_COLUMNS[1],
            },
        )
    ).all()
    by_name = {str(row.column_name): row for row in rows}

    missing = [name for name in REQUIRED_PROGRESS_COLUMNS if name not in by_name]
    if missing:
        raise RuntimeError(f"mode_progress is missing required columns: {missing}")

    for name in REQUIRED_PROGRESS_COLUMNS:
        row = by_name[name]
        nullable = str(row.is_nullable)
        if nullable != "NO":
            raise RuntimeError(f"mode_progress.{name} must be NOT NULL, got is_nullable={nullable}")
        default = "" if row.column_default is None else str(row.column_default)
        if "0" not in default:
            raise RuntimeError(f"mode_progress.{name} default must contain 0, got={default!r}")


async def _assert_canary_mode_starts_from_a1(mode_code: str) -> None:
    now_utc = datetime.now(timezone.utc)
    local_date = berlin_local_date(now_utc)

    async with SessionLocal() as session:
        await session.begin()
        try:
            user = await UsersRepo.create(
                session,
                telegram_user_id=90_000_000_000 + int(uuid4().hex[:10], 16),
                referral_code=f"R{uuid4().hex[:10]}",
                username=None,
                first_name="DeployCanary",
                referred_by_user_id=None,
            )
            start_result = await GameSessionService.start_session(
                session,
                user_id=user.id,
                mode_code=mode_code,
                source="MENU",
                idempotency_key=f"deploy-gate:{mode_code}:{uuid4().hex[:12]}",
                now_utc=now_utc,
                selection_seed_override=f"deploy-gate:{mode_code}:{uuid4().hex[:8]}",
            )
            question = await sessions_service_module.get_question_by_id(
                session,
                mode_code,
                question_id=start_result.session.question_id,
                local_date_berlin=local_date,
            )
            if question is None:
                raise RuntimeError(
                    f"canary mode={mode_code} question_id={start_result.session.question_id} not found"
                )
            if question.level != EXPECTED_START_LEVEL:
                raise RuntimeError(
                    f"canary mode={mode_code} expected level={EXPECTED_START_LEVEL}, got={question.level}"
                )
        finally:
            await session.rollback()


async def _run() -> int:
    expected_head = _expected_alembic_head()
    current_head = await _current_alembic_version()
    print(f"post_deploy_gate: alembic_expected={expected_head} db_current={current_head}")
    if current_head != expected_head:
        print("post_deploy_gate failed: alembic_version is not at head")
        return 1

    async with SessionLocal() as session:
        await _assert_progress_schema(session)
    print("post_deploy_gate: schema check OK")

    for mode_code in CANARY_MODES:
        await _assert_canary_mode_starts_from_a1(mode_code)
        print(f"post_deploy_gate: canary mode={mode_code} level={EXPECTED_START_LEVEL} OK")

    print("post_deploy_gate: all checks passed")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
