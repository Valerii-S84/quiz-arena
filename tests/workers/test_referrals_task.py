import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.workers.tasks import referrals, referrals_notifications


def test_run_referral_qualification_checks_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, batch_size: int) -> dict[str, int]:
        return {
            "examined": batch_size,
            "qualified": 2,
            "canceled": 1,
            "rejected_fraud": 0,
        }

    monkeypatch.setattr(referrals, "run_referral_qualification_checks_async", fake_async)

    result = referrals.run_referral_qualification_checks(batch_size=7)
    assert result["examined"] == 7
    assert result["qualified"] == 2


def test_run_referral_qualification_checks_sends_rejected_notifications(monkeypatch) -> None:
    async def fake_run_qualification_checks(
        session,
        *,
        now_utc,
        batch_size: int,
        on_rejected_fraud,
    ) -> dict[str, int]:
        del session, now_utc
        assert batch_size == 9
        assert on_rejected_fraud is not None
        await on_rejected_fraud(91, 42)
        return {
            "examined": 1,
            "qualified": 0,
            "canceled": 0,
            "rejected_fraud": 1,
        }

    async def fake_send_rejected_notifications(*, referrer_user_ids: list[int]) -> dict[str, int]:
        assert referrer_user_ids == [42]
        return {
            "rejected_user_notified": 1,
            "rejected_user_notify_failed": 0,
        }

    monkeypatch.setattr(
        referrals.ReferralService, "run_qualification_checks", fake_run_qualification_checks
    )
    monkeypatch.setattr(
        referrals,
        "_send_referral_rejected_notifications",
        fake_send_rejected_notifications,
    )

    result = asyncio.run(referrals.run_referral_qualification_checks_async(batch_size=9))
    assert result["examined"] == 1
    assert result["rejected_user_notified"] == 1


def test_run_referral_reward_distribution_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, batch_size: int) -> dict[str, int]:
        return {
            "referrers_examined": batch_size,
            "rewards_granted": 1,
            "deferred_limit": 0,
        }

    monkeypatch.setattr(referrals, "run_referral_reward_distribution_async", fake_async)

    result = referrals.run_referral_reward_distribution(batch_size=3)
    assert result["referrers_examined"] == 3
    assert result["rewards_granted"] == 1


def test_send_referral_reward_alerts_sends_milestone_and_reward_events(
    monkeypatch,
) -> None:
    events: list[str] = []
    recorded: list[tuple[str, bool]] = []

    async def fake_send_ops_alert(*, event: str, payload: dict[str, object]) -> bool:
        events.append(event)
        return True

    async def fake_record_event(*, event_type: str, payload: dict[str, int], sent: bool) -> None:
        recorded.append((event_type, sent))

    monkeypatch.setattr(referrals, "send_ops_alert", fake_send_ops_alert)
    monkeypatch.setattr(referrals, "_record_referral_reward_event", fake_record_event)

    result = asyncio.run(
        referrals._send_referral_reward_alerts(
            result={
                "referrers_examined": 1,
                "rewards_granted": 1,
                "deferred_limit": 0,
                "awaiting_choice": 2,
                "newly_notified": 2,
            }
        )
    )

    assert events == [
        "referral_reward_milestone_available",
        "referral_reward_granted",
    ]
    assert recorded == [
        ("referral_reward_milestone_available", True),
        ("referral_reward_granted", True),
    ]
    assert result == {
        "milestone_alert_sent": 1,
        "reward_alert_sent": 1,
    }


def test_send_referral_reward_alerts_skips_milestone_without_new_notifications(
    monkeypatch,
) -> None:
    events: list[str] = []

    async def fake_send_ops_alert(*, event: str, payload: dict[str, object]) -> bool:
        del payload
        events.append(event)
        return True

    async def fake_record_event(*, event_type: str, payload: dict[str, int], sent: bool) -> None:
        del event_type, payload, sent
        return None

    monkeypatch.setattr(referrals, "send_ops_alert", fake_send_ops_alert)
    monkeypatch.setattr(referrals, "_record_referral_reward_event", fake_record_event)

    result = asyncio.run(
        referrals._send_referral_reward_alerts(
            result={
                "rewards_granted": 0,
                "awaiting_choice": 3,
                "newly_notified": 0,
            }
        )
    )

    assert events == []
    assert result == {
        "milestone_alert_sent": 0,
        "reward_alert_sent": 0,
    }


def test_send_referral_ready_notifications_sends_only_new_targets(monkeypatch) -> None:
    now_utc = datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc)
    sent_messages: list[int] = []
    emitted_events: list[int] = []

    class _DummyBotSession:
        async def close(self) -> None:
            return None

    class _DummyBot:
        def __init__(self) -> None:
            self.session = _DummyBotSession()

        async def send_message(self, *, chat_id: int, text: str, reply_markup) -> None:
            del text, reply_markup
            sent_messages.append(chat_id)

    async def _fake_list_referrer_ids_with_reward_notifications(session, *, notified_at):
        del session
        assert notified_at == now_utc
        return [11]

    async def _fake_list_by_ids(session, user_ids):
        del session
        assert tuple(user_ids) == (11,)
        return [SimpleNamespace(id=11, telegram_user_id=22_000_000_011)]

    async def _fake_emit(session, *, event_type, source, happened_at, user_id, payload):
        del session, source, happened_at, payload
        assert event_type == "referral_reward_notified"
        emitted_events.append(int(user_id))

    monkeypatch.setattr(
        referrals_notifications.ReferralsRepo,
        "list_referrer_ids_with_reward_notifications",
        _fake_list_referrer_ids_with_reward_notifications,
    )
    monkeypatch.setattr(referrals_notifications.UsersRepo, "list_by_ids", _fake_list_by_ids)
    monkeypatch.setattr(referrals_notifications, "build_bot", lambda: _DummyBot())
    monkeypatch.setattr(referrals_notifications, "emit_analytics_event", _fake_emit)

    result = asyncio.run(referrals._send_referral_ready_notifications(notified_at=now_utc))

    assert sent_messages == [22_000_000_011]
    assert emitted_events == [11]
    assert result == {
        "reward_user_notified": 1,
        "reward_user_notify_failed": 0,
    }


def test_send_referral_rejected_notifications(monkeypatch) -> None:
    sent_messages: list[tuple[int, str]] = []

    class _DummyBotSession:
        async def close(self) -> None:
            return None

    class _DummyBot:
        def __init__(self) -> None:
            self.session = _DummyBotSession()

        async def send_message(self, *, chat_id: int, text: str) -> None:
            sent_messages.append((chat_id, text))

    async def _fake_list_by_ids(session, user_ids):
        del session
        assert set(user_ids) == {5, 8}
        return [
            SimpleNamespace(id=5, telegram_user_id=55_000_000_005),
            SimpleNamespace(id=8, telegram_user_id=55_000_000_008),
        ]

    monkeypatch.setattr(referrals_notifications.UsersRepo, "list_by_ids", _fake_list_by_ids)
    monkeypatch.setattr(referrals_notifications, "build_bot", lambda: _DummyBot())

    result = asyncio.run(
        referrals._send_referral_rejected_notifications(referrer_user_ids=[5, 8, 5])
    )

    assert len(sent_messages) == 3
    assert all("nicht anerkannt" in text for _, text in sent_messages)
    assert result == {
        "rejected_user_notified": 3,
        "rejected_user_notify_failed": 0,
    }
