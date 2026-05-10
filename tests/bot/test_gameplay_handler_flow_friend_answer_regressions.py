from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import friend_answer_flow
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import FriendChallengeExpiredError
from app.game.sessions.types import AnswerSessionResult, FriendChallengeSnapshot
from tests.bot.helpers import DummyCallback, DummySessionLocal


def _friend_result(*, status: str) -> AnswerSessionResult:
    return AnswerSessionResult(
        session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        question_id="q-friend",
        is_correct=True,
        current_streak=1,
        best_streak=1,
        idempotent_replay=False,
        mode_code="QUICK_MIX_A1A2",
        source="FRIEND_CHALLENGE",
        friend_challenge=FriendChallengeSnapshot(
            challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            invite_token="token",
            challenge_type="DIRECT",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status=status,
            creator_user_id=10,
            opponent_user_id=20,
            current_round=5,
            total_rounds=5,
            creator_score=0,
            opponent_score=5,
        ),
        friend_challenge_answered_round=5,
        friend_challenge_round_completed=True,
    )


def _friend_answer_context(**overrides) -> friend_answer_flow.FriendAnswerFlowContext:
    async def _home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=10, free_energy=10, paid_energy=0)

    async def _resolve_label(**kwargs):
        del kwargs
        return "Freund"

    async def _notify(*args, **kwargs):
        del args, kwargs

    async def _send_question(*args, **kwargs):
        del args, kwargs

    return friend_answer_flow.FriendAnswerFlowContext(
        services=friend_answer_flow.FriendAnswerFlowServices(
            session_local=DummySessionLocal(),
            user_onboarding_service=SimpleNamespace(
                ensure_home_snapshot=overrides.get("ensure_home_snapshot", _home_snapshot)
            ),
            game_session_service=SimpleNamespace(
                start_friend_challenge_round=overrides.get(
                    "start_friend_challenge_round",
                    lambda *args, **kwargs: None,
                )
            ),
        ),
        actions=friend_answer_flow.FriendAnswerFlowActions(
            notify_opponent=_notify,
            enqueue_friend_challenge_proof_cards=lambda **kwargs: None,
            send_friend_round_question=overrides.get("send_friend_round_question", _send_question),
        ),
        rendering=friend_answer_flow.FriendAnswerFlowRendering(
            resolve_opponent_label=overrides.get("resolve_opponent_label", _resolve_label),
            friend_opponent_user_id=lambda **kwargs: 20,
            build_friend_score_text=lambda **kwargs: "score",
            build_friend_ttl_text=lambda **kwargs: None,
            build_friend_finish_text=lambda **kwargs: "finish",
            build_public_badge_label=lambda **kwargs: "badge",
            build_friend_proof_card_text=lambda **kwargs: "proof",
            build_series_progress_text=lambda **kwargs: "series",
        ),
    )


@pytest.mark.asyncio
async def test_friend_answer_branch_rejects_missing_callback_fields() -> None:
    callback = DummyCallback(data="answer:test:0", from_user=None)
    callback.message = cast(Any, None)

    await friend_answer_flow.handle_friend_answer_branch(
        callback,
        result=_friend_result(status="ACTIVE"),
        now_utc=datetime(2026, 3, 9, 12, 0, 0),
        context=_friend_answer_context(),
    )

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_friend_answer_branch_reports_missing_friend_challenge() -> None:
    callback = DummyCallback(data="answer:test:0", from_user=SimpleNamespace(id=10))
    await friend_answer_flow.handle_friend_answer_branch(
        callback,
        result=AnswerSessionResult(
            session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            question_id="q-friend",
            is_correct=True,
            current_streak=1,
            best_streak=1,
            idempotent_replay=False,
            mode_code="QUICK_MIX_A1A2",
            source="FRIEND_CHALLENGE",
            friend_challenge=None,
        ),
        now_utc=datetime(2026, 3, 9, 12, 0, 0),
        context=_friend_answer_context(),
    )

    assert callback.message.answers[0].text == TEXTS_DE["msg.friend.challenge.invalid"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_friend_answer_branch_reports_expired_next_round() -> None:
    async def _expired_round(*args, **kwargs):
        del args, kwargs
        raise FriendChallengeExpiredError()

    callback = DummyCallback(data="answer:test:0", from_user=SimpleNamespace(id=10))
    await friend_answer_flow.handle_friend_answer_branch(
        callback,
        result=_friend_result(status="ACTIVE"),
        now_utc=datetime(2026, 3, 9, 12, 0, 0),
        context=_friend_answer_context(start_friend_challenge_round=_expired_round),
    )

    assert callback.message.answers[-1].text == TEXTS_DE["msg.friend.challenge.expired"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_friend_answer_branch_sends_next_round_question() -> None:
    async def _home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=10, free_energy=7, paid_energy=2)

    round_start = SimpleNamespace(
        snapshot=_friend_result(status="ACTIVE").friend_challenge,
        start_result=object(),
        already_answered_current_round=False,
    )

    async def _start_round(*args, **kwargs):
        del args, kwargs
        return round_start

    sent_questions: list[tuple[int, int, object]] = []

    async def _send_question(callback, **kwargs):
        del callback
        sent_questions.append(
            (
                kwargs["snapshot_free_energy"],
                kwargs["snapshot_paid_energy"],
                kwargs["round_start"],
            )
        )

    callback = DummyCallback(data="answer:test:0", from_user=SimpleNamespace(id=10))
    await friend_answer_flow.handle_friend_answer_branch(
        callback,
        result=_friend_result(status="ACTIVE"),
        now_utc=datetime(2026, 3, 9, 12, 0, 0),
        context=_friend_answer_context(
            ensure_home_snapshot=_home_snapshot,
            start_friend_challenge_round=_start_round,
            send_friend_round_question=_send_question,
        ),
    )

    assert sent_questions == [(7, 2, round_start)]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
