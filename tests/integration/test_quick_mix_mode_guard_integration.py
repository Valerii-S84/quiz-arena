from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.quiz_questions import QuizQuestion as QuizQuestionModel
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.questions.types import QuizQuestion
from app.game.sessions.service import GameSessionService

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=60_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="ModeGuard",
            referred_by_user_id=None,
        )
        return user.id


def _build_question(
    *,
    question_id: str,
    mode_code: str,
    level: str,
    now_utc: datetime,
) -> QuizQuestionModel:
    return QuizQuestionModel(
        question_id=question_id,
        mode_code=mode_code,
        source_file="quick_mix_mode_guard_seed.csv",
        level=level,
        category="ModeGuard",
        question_text=f"{mode_code} {level} {question_id}?",
        option_1="opt1",
        option_2="opt2",
        option_3="opt3",
        option_4="opt4",
        correct_option_id=0,
        correct_answer="opt1",
        explanation="Seed",
        key=question_id,
        status="ACTIVE",
        created_at=now_utc,
        updated_at=now_utc,
    )


@pytest.mark.asyncio
async def test_menu_quick_mix_mode_guard_retries_and_never_serves_foreign_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 2, 25, 20, 0, tzinfo=UTC)
    user_id = await _create_user("quick_mix_mode_guard")

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                _build_question(
                    question_id="quick_mix_guard_a1_001",
                    mode_code="QUICK_MIX_A1A2",
                    level="A1",
                    now_utc=now_utc,
                ),
                _build_question(
                    question_id="artikel_guard_b2_001",
                    mode_code="ARTIKEL_SPRINT",
                    level="B2",
                    now_utc=now_utc,
                ),
            ]
        )
        await session.flush()

        calls: list[str] = []
        guard_mode_lookups = 0

        async def fake_select_question_for_mode(  # noqa: ANN001
            db_session,
            mode_code,
            *,
            local_date_berlin,
            recent_question_ids,
            selection_seed,
            preferred_level=None,
        ):
            del db_session, mode_code, local_date_berlin, recent_question_ids, selection_seed
            calls.append("select")
            if len(calls) == 1:
                return QuizQuestion(
                    question_id="artikel_guard_b2_001",
                    text="Artikel guard",
                    options=("a", "b", "c", "d"),
                    correct_option=0,
                    mode_code="ARTIKEL_SPRINT",
                    level="B2",
                    category="Artikel",
                )
            return QuizQuestion(
                question_id="quick_mix_guard_a1_001",
                text="Quick Mix guard",
                options=("a", "b", "c", "d"),
                correct_option=0,
                mode_code="QUICK_MIX_A1A2",
                level="A1",
                category="QuickMix",
            )

        async def fake_guard_get_by_id(db_session, question_id):  # noqa: ANN001
            nonlocal guard_mode_lookups
            del db_session, question_id
            guard_mode_lookups += 1
            return None

        monkeypatch.setattr(
            "app.game.sessions.service.select_question_for_mode",
            fake_select_question_for_mode,
        )
        monkeypatch.setattr(
            "app.game.sessions.service.sessions_start_guard.QuizQuestionsRepo.get_by_id",
            fake_guard_get_by_id,
        )

        start = await GameSessionService.start_session(
            session,
            user_id=user_id,
            mode_code="QUICK_MIX_A1A2",
            source="MENU",
            idempotency_key="quick-mix:mode-guard:start",
            now_utc=now_utc,
        )

        assert start.session.question_id == "quick_mix_guard_a1_001"
        assert len(calls) == 2
        assert guard_mode_lookups == 0

        events = list(
            (
                await session.execute(
                    select(AnalyticsEvent)
                    .where(
                        AnalyticsEvent.user_id == user_id,
                        AnalyticsEvent.event_type.in_(
                            ("question_mode_mismatch", "question_level_served")
                        ),
                    )
                    .order_by(AnalyticsEvent.happened_at.asc(), AnalyticsEvent.id.asc())
                )
            ).scalars()
        )

        mismatch_events = [
            event for event in events if event.event_type == "question_mode_mismatch"
        ]
        served_events = [event for event in events if event.event_type == "question_level_served"]

        assert len(mismatch_events) == 1
        assert mismatch_events[0].payload["mode_code"] == "QUICK_MIX_A1A2"
        assert mismatch_events[0].payload["served_question_mode"] == "ARTIKEL_SPRINT"
        assert mismatch_events[0].payload["fallback_step"] == "initial"
        assert mismatch_events[0].payload["retry_count"] == 0
        assert mismatch_events[0].payload["mismatch_reason"] == "selector_returned_foreign_mode"

        assert len(served_events) == 1
        assert served_events[0].payload["expected_level"] == "A1"
        assert served_events[0].payload["served_level"] == "A1"
        assert served_events[0].payload["served_question_mode"] == "QUICK_MIX_A1A2"
        assert served_events[0].payload["fallback_step"] == "mode_retry"
        assert served_events[0].payload["retry_count"] == 1
        assert served_events[0].payload["mismatch_reason"] == "selector_returned_foreign_mode"


@pytest.mark.asyncio
async def test_menu_mode_guard_applies_to_non_quick_mix_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 2, 25, 20, 30, tzinfo=UTC)
    user_id = await _create_user("artikel_mode_guard")

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                _build_question(
                    question_id="artikel_guard_a1_001",
                    mode_code="ARTIKEL_SPRINT",
                    level="A1",
                    now_utc=now_utc,
                ),
                _build_question(
                    question_id="quick_mix_guard_a1_002",
                    mode_code="QUICK_MIX_A1A2",
                    level="A1",
                    now_utc=now_utc,
                ),
            ]
        )
        await session.flush()

        calls: list[str] = []

        async def fake_select_question_for_mode(  # noqa: ANN001
            db_session,
            mode_code,
            *,
            local_date_berlin,
            recent_question_ids,
            selection_seed,
            preferred_level=None,
        ):
            del db_session, mode_code, local_date_berlin, recent_question_ids, selection_seed
            calls.append("select")
            if len(calls) == 1:
                return QuizQuestion(
                    question_id="quick_mix_guard_a1_002",
                    text="Wrong mode",
                    options=("a", "b", "c", "d"),
                    correct_option=0,
                    mode_code="QUICK_MIX_A1A2",
                    level="A1",
                    category="QuickMix",
                )
            return QuizQuestion(
                question_id="artikel_guard_a1_001",
                text="Correct mode",
                options=("a", "b", "c", "d"),
                correct_option=0,
                mode_code="ARTIKEL_SPRINT",
                level="A1",
                category="Artikel",
            )

        monkeypatch.setattr(
            "app.game.sessions.service.select_question_for_mode",
            fake_select_question_for_mode,
        )

        start = await GameSessionService.start_session(
            session,
            user_id=user_id,
            mode_code="ARTIKEL_SPRINT",
            source="MENU",
            idempotency_key="artikel:mode-guard:start",
            now_utc=now_utc,
        )

        assert start.session.question_id == "artikel_guard_a1_001"
        assert len(calls) == 2

        mismatch_events = list(
            (
                await session.execute(
                    select(AnalyticsEvent)
                    .where(
                        AnalyticsEvent.user_id == user_id,
                        AnalyticsEvent.event_type == "question_mode_mismatch",
                    )
                    .order_by(AnalyticsEvent.happened_at.asc(), AnalyticsEvent.id.asc())
                )
            ).scalars()
        )
        assert len(mismatch_events) == 1
        assert mismatch_events[0].payload["mode_code"] == "ARTIKEL_SPRINT"
