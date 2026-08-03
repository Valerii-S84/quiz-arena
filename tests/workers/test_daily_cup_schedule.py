import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.bot.texts.de import TEXTS_DE
from app.core.config import Settings
from app.game.tournaments.daily_cup_slots import ROUND_SLOTS, get_round_deadline, get_round_start
from app.workers.tasks import daily_cup_async, daily_cup_schedule

ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE_PATHS = (
    ROOT / ".env.example",
    ROOT / ".env.production.example",
)
RUNTIME_DAILY_CUP_KEY_RE = re.compile(r'alias="(DAILY_CUP_[A-Z_]+)"')
RUNTIME_DAILY_CUP_OS_GETENV_RE = re.compile(r'os\.getenv\("(DAILY_CUP_[A-Z_]+)"')


def test_configure_daily_cup_schedule_uses_single_1600_registration_push(
    monkeypatch,
) -> None:
    monkeypatch.setattr(daily_cup_schedule, "DAILY_CUP_ENABLED", True)
    monkeypatch.setattr(daily_cup_schedule, "DAILY_CUP_OPEN_HOUR", 16)
    monkeypatch.setattr(daily_cup_schedule, "DAILY_CUP_OPEN_MINUTE", 0)
    monkeypatch.setattr(daily_cup_schedule, "DAILY_CUP_LAST_CALL_REMINDER_HOUR", 16)
    monkeypatch.setattr(daily_cup_schedule, "DAILY_CUP_LAST_CALL_REMINDER_MINUTE", 30)
    monkeypatch.setattr(daily_cup_schedule, "DAILY_CUP_PRESTART_REMINDER_HOUR", 16)
    monkeypatch.setattr(daily_cup_schedule, "DAILY_CUP_PRESTART_REMINDER_MINUTE", 50)
    monkeypatch.setattr(daily_cup_schedule, "DAILY_CUP_CLOSE_HOUR", 17)
    monkeypatch.setattr(daily_cup_schedule, "DAILY_CUP_CLOSE_MINUTE", 0)

    celery_app = SimpleNamespace(conf=SimpleNamespace(beat_schedule={}))

    daily_cup_schedule.configure_daily_cup_schedule(celery_app)

    schedule = celery_app.conf.beat_schedule
    assert "daily-cup-send-invite-registration" in schedule
    assert "daily-cup-send-invite" not in schedule
    assert "daily-cup-open-registration" not in schedule
    assert (
        schedule["daily-cup-send-invite-registration"]["task"]
        == "app.workers.tasks.daily_cup.send_invite_registration"
    )
    assert schedule["daily-cup-send-invite-registration"]["schedule"].hour == {16}
    assert schedule["daily-cup-send-invite-registration"]["schedule"].minute == {0}
    assert schedule["daily-cup-last-call-reminder"]["schedule"].hour == {16}
    assert schedule["daily-cup-last-call-reminder"]["schedule"].minute == {30}
    assert schedule["daily-cup-prestart-reminder"]["schedule"].hour == {16}
    assert schedule["daily-cup-prestart-reminder"]["schedule"].minute == {50}
    assert schedule["daily-cup-close-registration"]["schedule"].hour == {17}
    assert schedule["daily-cup-close-registration"]["schedule"].minute == {0}


def test_daily_cup_enabled_defaults_to_true() -> None:
    assert Settings.model_fields["daily_cup_enabled"].default is True


def test_configure_daily_cup_schedule_registers_no_entries_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(daily_cup_schedule, "DAILY_CUP_ENABLED", False)
    celery_app = SimpleNamespace(conf=SimpleNamespace(beat_schedule={}))

    daily_cup_schedule.configure_daily_cup_schedule(celery_app)

    assert not any(name.startswith("daily-cup-") for name in celery_app.conf.beat_schedule)


def test_configure_daily_cup_schedule_removes_only_daily_cup_entries_when_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setattr(daily_cup_schedule, "DAILY_CUP_ENABLED", False)
    unrelated_entry = {"task": "tests.unrelated"}
    celery_app = SimpleNamespace(
        conf=SimpleNamespace(
            beat_schedule={
                "daily-cup-existing-entry": {"task": "tests.daily_cup"},
                "unrelated-entry": unrelated_entry,
            }
        )
    )

    daily_cup_schedule.configure_daily_cup_schedule(celery_app)

    assert celery_app.conf.beat_schedule == {"unrelated-entry": unrelated_entry}


def test_daily_cup_env_examples_match_runtime_daily_cup_keys_and_defaults() -> None:
    config_messaging_text = (ROOT / "app/core/config_messaging.py").read_text(encoding="utf-8")
    daily_cup_config_text = (ROOT / "app/workers/tasks/daily_cup_config.py").read_text(
        encoding="utf-8"
    )
    runtime_keys = {
        *RUNTIME_DAILY_CUP_KEY_RE.findall(config_messaging_text),
        *RUNTIME_DAILY_CUP_OS_GETENV_RE.findall(daily_cup_config_text),
    }
    expected_daily_cup_lines = {
        "DAILY_CUP_ENABLED=true",
        "DAILY_CUP_INVITE_TIME=16:00",
        "DAILY_CUP_LAST_CALL_REMINDER_TIME=16:30",
        "DAILY_CUP_PRESTART_REMINDER_TIME=16:50",
        "DAILY_CUP_REGISTRATION_OPEN=16:00",
        "DAILY_CUP_REGISTRATION_CLOSE=17:00",
        "DAILY_CUP_MIN_PARTICIPANTS=4",
        "DAILY_CUP_TIMEZONE=Europe/Berlin",
        "DAILY_CUP_TURN_REMINDER_INTERVAL_MINUTES=10",
        "DAILY_CUP_TURN_RESPONSE_GRACE_MINUTES=15",
    }
    stale_keys = {
        "DAILY_CUP_OPEN_TIME",
        "DAILY_CUP_CLOSE_TIME",
        "DAILY_CUP_ADVANCE_SLOTS",
        "DAILY_CUP_TOURNAMENT_TYPE",
    }

    for path in ENV_EXAMPLE_PATHS:
        lines = path.read_text(encoding="utf-8").splitlines()
        example_keys = {
            line.split("=", maxsplit=1)[0]
            for line in lines
            if line.startswith("DAILY_CUP_") and "=" in line
        }
        assert example_keys == runtime_keys
        assert expected_daily_cup_lines.issubset(set(lines))
        assert not stale_keys.intersection(example_keys)


@pytest.mark.asyncio
async def test_daily_cup_registration_push_runtime_uses_active_text_key(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_send_daily_cup_registration_push_async(**kwargs):
        captured.update(kwargs)
        return {"processed": 1, "sent_total": 0}

    monkeypatch.setattr(
        daily_cup_async,
        "send_daily_cup_registration_push_async",
        _fake_send_daily_cup_registration_push_async,
    )

    await daily_cup_async.send_daily_cup_invite_registration_async()

    assert captured["text_key"] == "msg.daily_cup.push.registration"


def test_daily_cup_round_slots_cover_four_fixed_berlin_windows() -> None:
    berlin = ZoneInfo("Europe/Berlin")
    tournament_start = datetime(2026, 3, 1, 17, 0, tzinfo=berlin)

    assert ROUND_SLOTS == (
        (17, 0, 30),
        (17, 30, 30),
        (18, 0, 30),
        (18, 30, 30),
    )
    assert [
        get_round_start(round_number=round_number, tournament_start=tournament_start)
        .astimezone(berlin)
        .strftime("%H:%M")
        for round_number in range(1, 5)
    ] == ["17:00", "17:30", "18:00", "18:30"]
    assert [
        get_round_deadline(round_number=round_number, tournament_start=tournament_start)
        .astimezone(berlin)
        .strftime("%H:%M")
        for round_number in range(1, 5)
    ] == ["17:30", "18:00", "18:30", "19:00"]


def test_daily_cup_funnel_texts_use_active_registration_copy_and_no_old_1800_copy() -> None:
    funnel_text_keys = (
        "msg.daily_cup.push.registration",
        "msg.daily_cup.last_call_reminder",
        "msg.daily_cup.prestart_reminder",
    )

    for text_key in funnel_text_keys:
        text = TEXTS_DE[text_key]
        assert "ab 13 Spielern" in text
        assert "18:00" not in text

    active_registration_text = TEXTS_DE["msg.daily_cup.push.registration"]
    assert "Anmeldung ab 16:00" in active_registration_text
    assert "bis {close_time}" in active_registration_text
    assert "msg.daily_cup.invite_push" not in TEXTS_DE

    general_text_keys = (
        "msg.daily_cup.joined_confirmation",
        "msg.daily_cup.registered_waiting",
        "msg.daily_cup.not_finished_summary",
        "msg.daily_cup.no_tournament",
        "msg.daily_cup.not_participant",
    )
    for text_key in general_text_keys:
        text = TEXTS_DE[text_key]
        assert "18:00" not in text
        assert "17:00" in text
