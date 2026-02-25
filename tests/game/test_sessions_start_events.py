from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.game.sessions.service.sessions_start_events import (
    emit_question_level_served_event,
    emit_question_mode_mismatch_event,
)

UTC = timezone.utc


@pytest.mark.asyncio
async def test_emit_question_mode_mismatch_event_emits_alert_and_analytics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analytics_calls: list[dict[str, object]] = []
    alert_calls: list[dict[str, object]] = []

    async def fake_emit_analytics_event(session, **kwargs):  # noqa: ANN001
        del session
        analytics_calls.append(kwargs)

    async def fake_send_ops_alert(*, event: str, payload: dict[str, object]) -> bool:
        alert_calls.append({"event": event, "payload": payload})
        return True

    monkeypatch.setattr(
        "app.game.sessions.service.sessions_start_events.emit_analytics_event",
        fake_emit_analytics_event,
    )
    monkeypatch.setattr(
        "app.game.sessions.service.sessions_start_events.send_ops_alert",
        fake_send_ops_alert,
    )

    now_utc = datetime(2026, 2, 25, 18, 0, tzinfo=UTC)
    await emit_question_mode_mismatch_event(
        object(),
        user_id=11,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        expected_level="A1",
        served_level="B2",
        served_question_mode="ARTIKEL_SPRINT",
        question_id="q1",
        fallback_step="initial",
        retry_count=0,
        mismatch_reason="selector_returned_foreign_mode",
        now_utc=now_utc,
    )

    assert len(analytics_calls) == 1
    assert analytics_calls[0]["event_type"] == "question_mode_mismatch"
    assert len(alert_calls) == 1
    assert alert_calls[0]["event"] == "gameplay_question_mode_mismatch"


@pytest.mark.asyncio
async def test_emit_question_level_served_event_alerts_for_new_user_high_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analytics_calls: list[dict[str, object]] = []
    alert_calls: list[dict[str, object]] = []

    async def fake_emit_analytics_event(session, **kwargs):  # noqa: ANN001
        del session
        analytics_calls.append(kwargs)

    async def fake_send_ops_alert(*, event: str, payload: dict[str, object]) -> bool:
        alert_calls.append({"event": event, "payload": payload})
        return True

    async def fake_get_by_id(session, user_id):  # noqa: ANN001
        del session, user_id
        return SimpleNamespace(created_at=now_utc - timedelta(hours=1))

    monkeypatch.setattr(
        "app.game.sessions.service.sessions_start_events.emit_analytics_event",
        fake_emit_analytics_event,
    )
    monkeypatch.setattr(
        "app.game.sessions.service.sessions_start_events.send_ops_alert",
        fake_send_ops_alert,
    )
    monkeypatch.setattr(
        "app.game.sessions.service.sessions_start_events.UsersRepo.get_by_id",
        fake_get_by_id,
    )

    now_utc = datetime(2026, 2, 25, 18, 30, tzinfo=UTC)
    await emit_question_level_served_event(
        object(),
        user_id=12,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        expected_level="A1",
        served_level="B2",
        served_question_mode="QUICK_MIX_A1A2",
        question_id="q2",
        fallback_step="mode_retry",
        retry_count=1,
        mismatch_reason="selector_returned_foreign_mode",
        now_utc=now_utc,
    )

    assert len(analytics_calls) == 1
    assert analytics_calls[0]["event_type"] == "question_level_served"
    assert len(alert_calls) == 1
    assert alert_calls[0]["event"] == "gameplay_new_user_high_level_served"


@pytest.mark.asyncio
async def test_emit_question_level_served_event_skips_alert_for_low_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analytics_calls: list[dict[str, object]] = []
    alert_calls: list[dict[str, object]] = []
    get_user_calls = 0

    async def fake_emit_analytics_event(session, **kwargs):  # noqa: ANN001
        del session
        analytics_calls.append(kwargs)

    async def fake_send_ops_alert(*, event: str, payload: dict[str, object]) -> bool:
        del event, payload
        alert_calls.append({})
        return True

    async def fake_get_by_id(session, user_id):  # noqa: ANN001
        nonlocal get_user_calls
        del session, user_id
        get_user_calls += 1
        return SimpleNamespace(created_at=datetime(2026, 2, 25, 17, 0, tzinfo=UTC))

    monkeypatch.setattr(
        "app.game.sessions.service.sessions_start_events.emit_analytics_event",
        fake_emit_analytics_event,
    )
    monkeypatch.setattr(
        "app.game.sessions.service.sessions_start_events.send_ops_alert",
        fake_send_ops_alert,
    )
    monkeypatch.setattr(
        "app.game.sessions.service.sessions_start_events.UsersRepo.get_by_id",
        fake_get_by_id,
    )

    now_utc = datetime(2026, 2, 25, 19, 0, tzinfo=UTC)
    await emit_question_level_served_event(
        object(),
        user_id=13,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        expected_level="A1",
        served_level="A1",
        served_question_mode="QUICK_MIX_A1A2",
        question_id="q3",
        fallback_step="none",
        retry_count=0,
        mismatch_reason="none",
        now_utc=now_utc,
    )

    assert len(analytics_calls) == 1
    assert len(alert_calls) == 0
    assert get_user_calls == 0
