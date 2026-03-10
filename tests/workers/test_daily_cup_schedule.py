from types import SimpleNamespace

from app.workers.tasks.daily_cup_schedule import configure_daily_cup_schedule


def test_configure_daily_cup_schedule_uses_single_1600_registration_push() -> None:
    celery_app = SimpleNamespace(conf=SimpleNamespace(beat_schedule={}))

    configure_daily_cup_schedule(celery_app)

    schedule = celery_app.conf.beat_schedule
    assert "daily-cup-send-invite-registration" in schedule
    assert "daily-cup-send-invite" not in schedule
    assert "daily-cup-open-registration" not in schedule
    assert (
        schedule["daily-cup-send-invite-registration"]["task"]
        == "app.workers.tasks.daily_cup.send_invite_registration"
    )
