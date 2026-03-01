"""
Phase 2 Manual Checklist Simulation
Run: python scripts/simulate_phase2_manual_check.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

RESULTS: dict[str, str] = {}


class _FakeMessage:
    def __init__(self) -> None:
        self.answers: list[tuple[str | None, dict[str, Any]]] = []

    async def answer(self, text: str | None = None, **kwargs: Any) -> None:
        self.answers.append((text, kwargs))


class _FakeBot:
    def __init__(self) -> None:
        self.send_message = AsyncMock(return_value=None)


class _FakeCallback:
    def __init__(self, *, user_id: int, first_name: str, bot: _FakeBot) -> None:
        self.from_user = SimpleNamespace(id=user_id, first_name=first_name)
        self.message = _FakeMessage()
        self.bot = bot

    async def answer(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        return None


def _flatten_callbacks(keyboard) -> list[str]:
    callbacks: list[str] = []
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.callback_data:
                callbacks.append(button.callback_data)
    return callbacks


def _flatten_urls(keyboard) -> list[str]:
    urls: list[str] = []
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.url:
                urls.append(button.url)
    return urls


async def check_1_creator_notification() -> None:
    """Creator gets join notifications when users join the tournament."""

    print("\n[CHECK 1] Creator notification on join")
    from app.bot.handlers.gameplay_flows.tournament_lobby_flow import (
        handle_tournament_join_by_invite,
    )

    bot = _FakeBot()
    expected_names = {2: "Lena", 3: "Mark"}

    async def _fake_home_snapshot(session, *, telegram_user):
        del session
        return SimpleNamespace(user_id=int(telegram_user.id))

    async def _fake_join_private_tournament_by_code(*args: Any, **kwargs: Any):
        del args, kwargs
        return SimpleNamespace(joined_now=True)

    async def _fake_lobby(*args: Any, **kwargs: Any):
        del args
        viewer_user_id = int(kwargs["viewer_user_id"])
        participants = (
            (1, "Creator"),
            (2, "Lena"),
            (3, "Mark"),
        )
        current = tuple(
            SimpleNamespace(user_id=user_id, score=0)
            for user_id, _ in participants
            if user_id in {1, viewer_user_id} or viewer_user_id == 3
        )
        return SimpleNamespace(
            tournament=SimpleNamespace(
                tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                invite_code="abcdefabcdef",
                created_by=1,
                name="Test Turnier",
                format="QUICK_5",
                max_participants=8,
                current_round=0,
                status="REGISTRATION",
            ),
            participants=current,
            viewer_joined=True,
            viewer_is_creator=False,
            can_start=False,
            viewer_current_match_challenge_id=None,
            viewer_current_opponent_user_id=None,
        )

    async def _fake_list_by_ids(session, user_ids):
        del session
        return [
            SimpleNamespace(id=user_id, username=None, first_name=f"user_{user_id}")
            for user_id in user_ids
        ]

    async def _fake_get_by_id(session, user_id: int):
        del session
        if user_id == 1:
            return SimpleNamespace(id=1, telegram_user_id=1)
        return None

    async def _fake_emit(*args: Any, **kwargs: Any):
        del args, kwargs
        return None

    tournament_service = SimpleNamespace(
        join_private_tournament_by_code=_fake_join_private_tournament_by_code,
        get_private_tournament_lobby_by_invite_code=_fake_lobby,
    )
    users_repo = SimpleNamespace(list_by_ids=_fake_list_by_ids, get_by_id=_fake_get_by_id)
    user_onboarding_service = SimpleNamespace(ensure_home_snapshot=_fake_home_snapshot)

    for joiner_id, joiner_name in expected_names.items():
        callback = _FakeCallback(user_id=joiner_id, first_name=joiner_name, bot=bot)
        await handle_tournament_join_by_invite(
            cast(Any, callback),
            invite_code="abcdefabcdef",
            session_local=SimpleNamespace(begin=lambda: _FakeSessionBegin()),
            user_onboarding_service=user_onboarding_service,
            tournament_service=tournament_service,
            users_repo=users_repo,
            emit_analytics_event=_fake_emit,
            event_source_bot="BOT",
        )
        call = bot.send_message.await_args_list[-1]
        assert int(call.kwargs["chat_id"]) == 1
        assert expected_names[joiner_id] in str(call.kwargs["text"])

    RESULTS["CHECK 1"] = "✅"
    print("   PASSED")


class _FakeSessionBegin:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False


async def check_2_no_revanche_button() -> None:
    """Tournament post-match keyboard must not contain rematch button."""

    print("\n[CHECK 2] No Revanche button after tournament match")
    from app.bot.handlers.gameplay_flows.tournament_match_post_flow import (
        build_tournament_post_match_keyboard,
    )

    keyboard = build_tournament_post_match_keyboard(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    )
    callbacks = _flatten_callbacks(keyboard)
    assert not any(
        ("revanche" in callback.lower() or "rematch" in callback.lower())
        for callback in callbacks
    )
    assert any(("standings" in callback.lower() or "tournament" in callback.lower()) for callback in callbacks)
    RESULTS["CHECK 2"] = "✅"
    print("   PASSED")


async def check_3_tabelle_teilen() -> None:
    """Standings keyboard must include share URL button."""

    print("\n[CHECK 3] Tabelle teilen button exists")
    from app.bot.keyboards.tournament import build_tournament_lobby_keyboard
    from app.workers.tasks.tournaments_messaging import (
        _build_standings_share_url,
        _with_standings_share_button,
    )

    base_keyboard = build_tournament_lobby_keyboard(
        invite_code="abcdefabcdef",
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        can_join=False,
        can_start=False,
        play_challenge_id=None,
        show_share_result=True,
    )
    share_url = _build_standings_share_url(
        bot_username="quizarenabot",
        invite_code="abcdefabcdef",
        tournament_name="Test Turnier",
    )
    keyboard = _with_standings_share_button(keyboard=base_keyboard, share_url=share_url)
    urls = _flatten_urls(keyboard)
    assert any("t.me/share/url" in url for url in urls)
    RESULTS["CHECK 3"] = "✅"
    print("   PASSED")


async def check_4_early_advance() -> None:
    """When pending matches become zero, round advances immediately."""

    print("\n[CHECK 4] Early round advance when all matches are done")
    from app.game.tournaments.constants import TOURNAMENT_STATUS_ROUND_1
    from app.game.tournaments.lifecycle import check_and_advance_round

    tournament_id = uuid4()
    now_utc = datetime.now(timezone.utc)
    fake_tournament = SimpleNamespace(
        id=tournament_id,
        status=TOURNAMENT_STATUS_ROUND_1,
        current_round=1,
    )

    with (
        patch(
            "app.game.tournaments.lifecycle.TournamentsRepo.get_by_id_for_update",
            new=AsyncMock(return_value=fake_tournament),
        ),
        patch(
            "app.game.tournaments.lifecycle.TournamentMatchesRepo.count_pending_for_tournament_round",
            new=AsyncMock(return_value=0),
        ),
        patch(
            "app.game.tournaments.lifecycle.settle_round_and_advance",
            new=AsyncMock(
                return_value={
                    "matches_settled": 1,
                    "matches_created": 1,
                    "round_started": 1,
                    "tournament_completed": 0,
                }
            ),
        ) as advance_mock,
    ):
        result = await check_and_advance_round(
            session=cast(Any, object()),
            tournament_id=tournament_id,
            now_utc=now_utc,
        )
        assert result["round_started"] == 1
        assert advance_mock.await_count == 1

    RESULTS["CHECK 4"] = "✅"
    print("   PASSED")


async def check_5_proof_card() -> None:
    """Generate and persist real proof card PNG."""

    print("\n[CHECK 5] Proof card generation")
    from app.workers.tasks.tournaments_proof_card_render import render_tournament_proof_card_png

    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(exist_ok=True)
    output_path = artifacts_dir / "proof_card_sample.png"

    image_bytes = render_tournament_proof_card_png(
        player_label="Max Mustermann",
        place=2,
        points="2.5",
        format_label="12 Fragen",
        completed_at=datetime.now(timezone.utc),
        tournament_name="Test Turnier",
        rounds_played=3,
    )
    output_path.write_bytes(image_bytes)

    assert output_path.exists(), "Proof card file was not created"
    size_bytes = output_path.stat().st_size
    assert size_bytes > 50_000, f"Proof card too small: {size_bytes} bytes"

    RESULTS["CHECK 5"] = f"✅ {size_bytes // 1024}KB"
    print(f"   PASSED ({size_bytes // 1024}KB)")


async def _run_check(name: str, check_fn) -> None:
    try:
        await check_fn()
    except Exception as exc:  # noqa: BLE001
        RESULTS[name] = f"❌ ({type(exc).__name__}: {exc})"
        print(f"   FAILED: {type(exc).__name__}: {exc}")


async def main() -> None:
    print("=" * 60)
    print("PHASE 2 - MANUAL CHECKLIST SIMULATION")
    print("=" * 60)

    await _run_check("CHECK 1", check_1_creator_notification)
    await _run_check("CHECK 2", check_2_no_revanche_button)
    await _run_check("CHECK 3", check_3_tabelle_teilen)
    await _run_check("CHECK 4", check_4_early_advance)
    await _run_check("CHECK 5", check_5_proof_card)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"CHECK 1 (creator notify):     {RESULTS.get('CHECK 1', '⚠️')}")
    print(f"CHECK 2 (no revanche):        {RESULTS.get('CHECK 2', '⚠️')}")
    print(f"CHECK 3 (tabelle teilen):     {RESULTS.get('CHECK 3', '⚠️')}")
    print(f"CHECK 4 (early advance):      {RESULTS.get('CHECK 4', '⚠️')}")
    print(f"CHECK 5 (proof card PNG):     {RESULTS.get('CHECK 5', '⚠️')}")

    all_passed = all(status.startswith("✅") for status in RESULTS.values()) and len(RESULTS) == 5
    print("\n" + "=" * 60)
    if all_passed:
        print("GATE: ✅ PASSED")
    else:
        print("GATE: ❌ FAILED")
    print("=" * 60)

    proof_path = Path("artifacts/proof_card_sample.png")
    if proof_path.exists():
        print(f"Proof card: {proof_path.absolute()}")


if __name__ == "__main__":
    asyncio.run(main())
