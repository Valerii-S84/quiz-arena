from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import friend_answer_flow
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import AnswerSessionResult, FriendChallengeSnapshot
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


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
            winner_user_id=None,
        ),
        friend_challenge_answered_round=5,
        friend_challenge_round_completed=True,
        friend_challenge_waiting_for_opponent=False,
    )


@pytest.mark.asyncio
async def test_friend_answer_branch_notifies_creator_once_when_opponent_finishes_all(
    monkeypatch,
) -> None:
    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=20, free_energy=20, paid_energy=0)

    async def _fake_get_by_id(session, challenge_id):
        del session, challenge_id
        return SimpleNamespace(
            creator_user_id=10,
            creator_answered_round=0,
            opponent_answered_round=5,
            total_rounds=5,
        )

    async def _fake_reserve_duel_push_slot(**kwargs):
        del kwargs
        return True

    async def _fake_resolve_label(**kwargs):
        del kwargs
        return "Freund"

    async def _fake_start_round(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(
            snapshot=_friend_result(status="OPPONENT_DONE").friend_challenge,
            start_result=None,
            already_answered_current_round=True,
        )

    notifications: list[tuple[int, str, str | None]] = []

    async def _fake_notify(callback, *, opponent_user_id, text, reply_markup=None):
        del callback
        callback_data = None
        if reply_markup is not None:
            callback_data = reply_markup.inline_keyboard[0][0].callback_data
        notifications.append((opponent_user_id, text, callback_data))

    monkeypatch.setattr(
        friend_answer_flow.FriendChallengesRepo,
        "get_by_id",
        _fake_get_by_id,
    )
    monkeypatch.setattr(
        friend_answer_flow,
        "reserve_duel_push_slot",
        _fake_reserve_duel_push_slot,
    )

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:0",
        from_user=SimpleNamespace(id=20),
        message=DummyMessage(),
    )
    await friend_answer_flow.handle_friend_answer_branch(
        callback,
        result=_friend_result(status="OPPONENT_DONE"),
        now_utc=datetime(2026, 3, 9, 12, 0, 0),
        session_local=DummySessionLocal(),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_home_snapshot),
        game_session_service=SimpleNamespace(start_friend_challenge_round=_fake_start_round),
        resolve_opponent_label=_fake_resolve_label,
        notify_opponent=_fake_notify,
        friend_opponent_user_id=lambda **kwargs: 10,
        build_friend_score_text=lambda **kwargs: "score",
        build_friend_ttl_text=lambda **kwargs: None,
        build_friend_finish_text=lambda **kwargs: "finish",
        build_public_badge_label=lambda **kwargs: "badge",
        build_friend_proof_card_text=lambda **kwargs: "proof",
        enqueue_friend_challenge_proof_cards=lambda **kwargs: None,
        build_series_progress_text=lambda **kwargs: "series",
        send_friend_round_question=lambda **kwargs: None,
    )

    assert notifications == [
        (
            10,
            TEXTS_DE["msg.friend.challenge.turn.reminder"],
            "friend:next:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        )
    ]


@pytest.mark.asyncio
async def test_friend_answer_branch_skips_push_when_creator_already_started(
    monkeypatch,
) -> None:
    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=20, free_energy=20, paid_energy=0)

    async def _fake_get_by_id(session, challenge_id):
        del session, challenge_id
        return SimpleNamespace(
            creator_user_id=10,
            creator_answered_round=1,
            opponent_answered_round=5,
            total_rounds=5,
        )

    async def _fake_resolve_label(**kwargs):
        del kwargs
        return "Freund"

    async def _fake_start_round(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(
            snapshot=_friend_result(status="OPPONENT_DONE").friend_challenge,
            start_result=None,
            already_answered_current_round=True,
        )

    notifications: list[int] = []

    async def _fake_notify(callback, *, opponent_user_id, text, reply_markup=None):
        del callback, text, reply_markup
        notifications.append(opponent_user_id)

    monkeypatch.setattr(
        friend_answer_flow.FriendChallengesRepo,
        "get_by_id",
        _fake_get_by_id,
    )

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:0",
        from_user=SimpleNamespace(id=20),
        message=DummyMessage(),
    )
    await friend_answer_flow.handle_friend_answer_branch(
        callback,
        result=_friend_result(status="OPPONENT_DONE"),
        now_utc=datetime(2026, 3, 9, 12, 0, 0),
        session_local=DummySessionLocal(),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_home_snapshot),
        game_session_service=SimpleNamespace(start_friend_challenge_round=_fake_start_round),
        resolve_opponent_label=_fake_resolve_label,
        notify_opponent=_fake_notify,
        friend_opponent_user_id=lambda **kwargs: 10,
        build_friend_score_text=lambda **kwargs: "score",
        build_friend_ttl_text=lambda **kwargs: None,
        build_friend_finish_text=lambda **kwargs: "finish",
        build_public_badge_label=lambda **kwargs: "badge",
        build_friend_proof_card_text=lambda **kwargs: "proof",
        enqueue_friend_challenge_proof_cards=lambda **kwargs: None,
        build_series_progress_text=lambda **kwargs: "series",
        send_friend_round_question=lambda **kwargs: None,
    )

    assert notifications == []


@pytest.mark.asyncio
async def test_friend_answer_branch_skips_repo_lookup_when_creator_answers(
    monkeypatch,
) -> None:
    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=10, free_energy=20, paid_energy=0)

    async def _fake_resolve_label(**kwargs):
        del kwargs
        return "Freund"

    async def _unexpected_get_by_id(session, challenge_id):
        del session, challenge_id
        raise AssertionError("repo lookup is not expected for creator answers")

    async def _fake_handle_completed(*args, **kwargs):
        del args, kwargs
        return None

    monkeypatch.setattr(
        friend_answer_flow.FriendChallengesRepo,
        "get_by_id",
        _unexpected_get_by_id,
    )
    monkeypatch.setattr(
        friend_answer_flow,
        "handle_completed_friend_challenge",
        _fake_handle_completed,
    )

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:0",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )
    await friend_answer_flow.handle_friend_answer_branch(
        callback,
        result=_friend_result(status="COMPLETED"),
        now_utc=datetime(2026, 3, 9, 12, 0, 0),
        session_local=DummySessionLocal(),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_home_snapshot),
        game_session_service=SimpleNamespace(start_friend_challenge_round=None),
        resolve_opponent_label=_fake_resolve_label,
        notify_opponent=lambda **kwargs: None,
        friend_opponent_user_id=lambda **kwargs: 20,
        build_friend_score_text=lambda **kwargs: "score",
        build_friend_ttl_text=lambda **kwargs: None,
        build_friend_finish_text=lambda **kwargs: "finish",
        build_public_badge_label=lambda **kwargs: "badge",
        build_friend_proof_card_text=lambda **kwargs: "proof",
        enqueue_friend_challenge_proof_cards=lambda **kwargs: None,
        build_series_progress_text=lambda **kwargs: "series",
        send_friend_round_question=lambda **kwargs: None,
    )
