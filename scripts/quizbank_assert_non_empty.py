from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.db.models.quiz_questions import QuizQuestion
from app.db.session import SessionLocal


async def _run() -> int:
    async with SessionLocal() as session:
        total = int((await session.execute(select(func.count()).select_from(QuizQuestion))).scalar_one())

    print(f"quizbank_assert_non_empty total={total}")  # noqa: T201
    if total <= 0:
        print("quizbank_assert_non_empty failed: quiz_questions table is empty")  # noqa: T201
        return 1
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
