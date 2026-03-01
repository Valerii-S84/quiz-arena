"""
Phase 3 Manual Checklist Simulation (Daily Arena Cup)
Run: python scripts/simulate_phase3_daily_cup_manual_check.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

RESULTS: dict[str, str] = {}


class _FakeMessage:
    def __init__(self) -> None:
        self.answers: list[tuple[str | None, dict[str, Any]]] = []

    async def answer(self, text: str | None = None, **kwargs: Any) -> None:
        self.answers.append((text, kwargs))


class _FakeCallback:
    def __init__(self, *, data: str) -> None:
        self.data = data
        self.message = _FakeMessage()


def _flatten_callbacks(keyboard) -> list[str]:
    callbacks: list[str] = []
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.callback_data:
                callbacks.append(button.callback_data)
    return callbacks


async def check_1_registration_keyboard() -> None:
    print("\n[CHECK 1] Daily Cup registration keyboard")
    from app.bot.keyboards.daily_cup import build_daily_cup_registration_keyboard

    keyboard = build_daily_cup_registration_keyboard(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    )
    callbacks = _flatten_callbacks(keyboard)
    assert callbacks == ["daily:cup:join:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]
    RESULTS["CHECK 1"] = "✅"
    print("   PASSED")


async def check_2_lobby_keyboard() -> None:
    print("\n[CHECK 2] Daily Cup lobby keyboard")
    from app.bot.keyboards.daily_cup import build_daily_cup_lobby_keyboard

    keyboard = build_daily_cup_lobby_keyboard(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        can_join=True,
        play_challenge_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        show_share_result=True,
    )
    callbacks = set(_flatten_callbacks(keyboard))
    assert "daily:cup:join:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert "friend:next:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" in callbacks
    assert "daily:cup:share:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert "daily:cup:view:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    RESULTS["CHECK 2"] = "✅"
    print("   PASSED")


async def check_3_schedule_config() -> None:
    print("\n[CHECK 3] Daily Cup beat schedule keys")
    import app.workers.tasks.daily_cup  # noqa: F401
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule or {}
    required = {
        "daily-cup-open-registration",
        "daily-cup-close-registration",
        "daily-cup-round-advance",
    }
    assert required.issubset(set(schedule.keys()))
    RESULTS["CHECK 3"] = "✅"
    print("   PASSED")


async def check_4_proof_card() -> None:
    print("\n[CHECK 4] Daily Arena proof card generation")
    from app.workers.tasks.tournaments_proof_card_render import render_tournament_proof_card_png

    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(exist_ok=True)
    output_path = artifacts_dir / "proof_card_daily_arena.png"

    image_bytes = render_tournament_proof_card_png(
        player_label="Max Mustermann",
        place=4,
        points="2",
        format_label="5 Fragen",
        completed_at=datetime.now(timezone.utc),
        tournament_name="Daily Arena Cup",
        rounds_played=3,
        is_daily_arena=True,
    )
    output_path.write_bytes(image_bytes)

    assert output_path.exists(), "Daily proof card file was not created"
    size_bytes = output_path.stat().st_size
    assert size_bytes > 50_000, f"Daily proof card too small: {size_bytes} bytes"

    RESULTS["CHECK 4"] = f"✅ {size_bytes // 1024}KB"
    print(f"   PASSED ({size_bytes // 1024}KB)")


async def _run_check(name: str, check_fn) -> None:
    try:
        await check_fn()
    except Exception as exc:  # noqa: BLE001
        RESULTS[name] = f"❌ ({type(exc).__name__}: {exc})"
        print(f"   FAILED: {type(exc).__name__}: {exc}")


async def main() -> None:
    print("=" * 60)
    print("PHASE 3 - DAILY CUP MANUAL CHECKLIST SIMULATION")
    print("=" * 60)

    await _run_check("CHECK 1", check_1_registration_keyboard)
    await _run_check("CHECK 2", check_2_lobby_keyboard)
    await _run_check("CHECK 3", check_3_schedule_config)
    await _run_check("CHECK 4", check_4_proof_card)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"CHECK 1 (join keyboard):       {RESULTS.get('CHECK 1', '⚠️')}")
    print(f"CHECK 2 (lobby keyboard):      {RESULTS.get('CHECK 2', '⚠️')}")
    print(f"CHECK 3 (beat schedule):       {RESULTS.get('CHECK 3', '⚠️')}")
    print(f"CHECK 4 (proof card PNG):      {RESULTS.get('CHECK 4', '⚠️')}")

    all_passed = all(status.startswith("✅") for status in RESULTS.values()) and len(RESULTS) == 4
    print("\n" + "=" * 60)
    print("GATE: ✅ PASSED" if all_passed else "GATE: ❌ FAILED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
