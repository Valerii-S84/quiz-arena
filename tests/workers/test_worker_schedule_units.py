from __future__ import annotations

from types import SimpleNamespace

from app.workers.tasks import (
    arena_duels_schedule,
    daily_challenge_schedule,
    friend_challenges_schedule,
    payments_reliability_schedule,
    tournaments_schedule,
)


def _app_with_schedule(initial=None):
    return SimpleNamespace(conf=SimpleNamespace(beat_schedule=initial))


def test_simple_worker_schedules_initialize_empty_schedule() -> None:
    app = _app_with_schedule(None)
    arena_duels_schedule.configure_arena_duels_schedule(app)
    assert app.conf.beat_schedule["arena-duel-expiry-every-5-minutes"]["schedule"] == 300.0

    app = _app_with_schedule(None)
    friend_challenges_schedule.configure_friend_challenges_schedule(app)
    assert (
        app.conf.beat_schedule["friend-challenge-deadlines-every-5-minutes"]["task"]
        == "app.workers.tasks.friend_challenges.run_friend_challenge_deadlines"
    )

    app = _app_with_schedule(None)
    tournaments_schedule.configure_private_tournaments_schedule(app)
    assert (
        app.conf.beat_schedule["private-tournaments-round-lifecycle"]["task"]
        == "app.workers.tasks.tournaments.run_private_tournament_rounds"
    )


def test_payments_reliability_schedule_preserves_existing_entries() -> None:
    app = _app_with_schedule({"existing": {"task": "keep"}})

    payments_reliability_schedule.configure_payments_reliability_schedule(app)

    schedule = app.conf.beat_schedule
    assert schedule["existing"] == {"task": "keep"}
    assert schedule["recover-paid-uncredited-every-5-minutes"]["options"] == {"queue": "q_high"}
    assert schedule["payment-invariant-alerts-every-minute"] == {
        "task": "app.workers.tasks.payments_reliability.run_payment_invariant_alerts",
        "schedule": 60.0,
        "options": {"queue": "q_high"},
    }
    assert schedule["payments-reconciliation-daily-0330-berlin"]["schedule"].hour == {3}
    assert schedule["payments-reconciliation-daily-0330-berlin"]["schedule"].minute == {30}


def test_daily_challenge_schedule_registers_three_jobs(monkeypatch) -> None:
    monkeypatch.setattr(daily_challenge_schedule, "DAILY_PRECOMPUTE_HOUR_BERLIN", 5)
    monkeypatch.setattr(daily_challenge_schedule, "DAILY_PRECOMPUTE_MINUTE_BERLIN", 10)
    monkeypatch.setattr(daily_challenge_schedule, "DAILY_PUSH_HOUR_BERLIN", 8)
    monkeypatch.setattr(daily_challenge_schedule, "DAILY_PUSH_MINUTE_BERLIN", 15)
    app = _app_with_schedule({})

    daily_challenge_schedule.configure_daily_challenge_schedule(app)

    schedule = app.conf.beat_schedule
    assert set(schedule) == {
        "daily-question-set-precompute-berlin",
        "daily-push-notifications-berlin",
        "daily-push-evening-reminder-berlin",
    }
    assert schedule["daily-question-set-precompute-berlin"]["schedule"].hour == {5}
    assert schedule["daily-push-notifications-berlin"]["schedule"].minute == {15}
    assert schedule["daily-push-evening-reminder-berlin"]["kwargs"] == {
        "push_kind": "EVENING_REMINDER"
    }
