from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_finished_keyboard,
    build_friend_challenge_limit_keyboard,
    build_friend_challenge_next_keyboard,
    build_friend_challenge_result_share_keyboard,
    build_friend_challenge_share_confirmed_keyboard,
    build_friend_challenge_share_keyboard,
    build_friend_challenge_share_url,
    build_friend_challenge_start_keyboard,
    build_friend_open_taken_keyboard,
    build_friend_pending_expired_keyboard,
)
from app.game.duels import rollout as duel_rollout
from app.game.sessions.types import FriendChallengeSnapshot


def test_friend_challenge_next_keyboard_contains_next_and_back() -> None:
    keyboard = build_friend_challenge_next_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001"
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "friend:next:00000000-0000-0000-0000-000000000001" in callbacks
    assert "home:open" in callbacks


def test_friend_challenge_back_keyboard_contains_home_only() -> None:
    keyboard = build_friend_challenge_back_keyboard()
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert callbacks == ["home:open"]


def test_friend_challenge_back_keyboard_shows_publish_only_for_creator_baseline() -> None:
    keyboard = build_friend_challenge_back_keyboard(
        challenge=FriendChallengeSnapshot(
            challenge_id=UUID("00000000-0000-0000-0000-000000000001"),
            invite_token="token",
            challenge_type="DIRECT",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status="CREATOR_DONE",
            creator_user_id=17,
            opponent_user_id=None,
            current_round=7,
            total_rounds=7,
            creator_score=6,
            opponent_score=0,
            creator_finished_at=datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),
        ),
        user_id=17,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.text for button in buttons] == [
        "🏟 In der Arena veröffentlichen",
        "↩️ Zurück",
    ]
    assert [button.callback_data for button in buttons] == [
        "arena:publish_friend:00000000-0000-0000-0000-000000000001",
        "home:open",
    ]


def test_friend_challenge_back_keyboard_hides_publish_when_rollout_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(duel_rollout, "is_canonical_duels_enabled", lambda: False)
    keyboard = build_friend_challenge_back_keyboard(
        challenge=FriendChallengeSnapshot(
            challenge_id=UUID("00000000-0000-0000-0000-000000000001"),
            invite_token="token",
            challenge_type="DIRECT",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status="CREATOR_DONE",
            creator_user_id=17,
            opponent_user_id=None,
            current_round=7,
            total_rounds=7,
            creator_score=6,
            opponent_score=0,
            creator_finished_at=datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),
        ),
        user_id=17,
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert callbacks == ["home:open"]


def test_friend_challenge_finished_keyboard_contains_rematch_and_back() -> None:
    keyboard = build_friend_challenge_finished_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001"
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    labels = [button.text for button in buttons]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert labels == ["📤 Ergebnis teilen", "🔄 Revanche", "🏠 Menü"]
    assert "friend:share:result:00000000-0000-0000-0000-000000000001" in callbacks
    assert "friend:rematch:00000000-0000-0000-0000-000000000001" in callbacks
    assert "home:open" in callbacks


def test_friend_challenge_finished_keyboard_can_hide_share() -> None:
    keyboard = build_friend_challenge_finished_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001",
        include_share=False,
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "friend:rematch:00000000-0000-0000-0000-000000000001" in callbacks
    assert "friend:share:result:00000000-0000-0000-0000-000000000001" not in callbacks
    assert "home:open" in callbacks


def test_friend_challenge_finished_keyboard_ignores_direct_share_url() -> None:
    keyboard = build_friend_challenge_finished_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001",
        share_url="https://t.me/share/url?url=x&text=y",
    )
    share_button = keyboard.inline_keyboard[0][0]
    assert share_button.url is None
    assert share_button.callback_data == "friend:share:result:00000000-0000-0000-0000-000000000001"


def test_friend_challenge_finished_keyboard_hides_rematch_when_rollout_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(duel_rollout, "is_canonical_duels_enabled", lambda: False)
    keyboard = build_friend_challenge_finished_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001"
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert callbacks == [
        "friend:share:result:00000000-0000-0000-0000-000000000001",
        "home:open",
    ]


def test_friend_challenge_limit_keyboard_contains_buy_options_and_back() -> None:
    keyboard = build_friend_challenge_limit_keyboard()
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "buy:FRIEND_CHALLENGE_5" in callbacks
    assert "buy:PREMIUM_WEEK" in callbacks
    assert "home:open" in callbacks


def test_friend_open_taken_keyboard_redirects_to_canonical_friend_duel_create() -> None:
    keyboard = build_friend_open_taken_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.text for button in buttons] == [
        "⚔️ Freundesduell erstellen",
        "↩️ Zurück",
    ]
    assert [button.callback_data for button in buttons] == [
        "friend:challenge:format:direct:7",
        "home:open",
    ]


def test_friend_pending_expired_keyboard_omits_publish_without_baseline() -> None:
    keyboard = build_friend_pending_expired_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001",
        can_publish_to_arena=False,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert [button.text for button in buttons] == [
        "⏳ Weiter warten",
        "❌ Schließen",
    ]
    assert callbacks == [
        "home:open",
        "friend:delete:00000000-0000-0000-0000-000000000001",
    ]
    assert "friend:open:repost:00000000-0000-0000-0000-000000000001" not in callbacks


def test_friend_pending_expired_keyboard_shows_publish_for_canonical_arena_path() -> None:
    keyboard = build_friend_pending_expired_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001",
        can_publish_to_arena=True,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert [button.text for button in buttons] == [
        "🏟 In der Arena veröffentlichen",
        "⏳ Weiter warten",
        "❌ Schließen",
    ]
    assert callbacks == [
        "arena:publish_friend:00000000-0000-0000-0000-000000000001",
        "home:open",
        "friend:delete:00000000-0000-0000-0000-000000000001",
    ]
    assert "friend:open:repost:00000000-0000-0000-0000-000000000001" not in callbacks


def test_friend_pending_expired_keyboard_hides_publish_when_rollout_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(duel_rollout, "is_canonical_duels_enabled", lambda: False)
    keyboard = build_friend_pending_expired_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001",
        can_publish_to_arena=True,
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert callbacks == [
        "home:open",
        "friend:delete:00000000-0000-0000-0000-000000000001",
    ]


def test_friend_challenge_share_keyboard_omits_accept_url_for_creator() -> None:
    keyboard = build_friend_challenge_share_keyboard(
        invite_link="https://t.me/quizarena_bot?start=fc_token",
        challenge_id="00000000-0000-0000-0000-000000000001",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.text for button in buttons] == [
        "📤 Teilen ->",
        "✅ Einladung gesendet",
        "⚔️ Jetzt spielen",
        "⏳ Auf Freund warten",
    ]
    assert not any(button.url and "duel_" in button.url for button in buttons)
    inline_queries = [
        button.switch_inline_query for button in buttons if button.switch_inline_query
    ]
    assert inline_queries == ["invite:duel:00000000-0000-0000-0000-000000000001"]
    assert any(
        button.callback_data == "friend:invite:sent:00000000-0000-0000-0000-000000000001"
        for button in buttons
    )
    assert any(
        button.callback_data == "friend:invite:required:00000000-0000-0000-0000-000000000001"
        for button in buttons
    )
    assert not any(
        button.callback_data == "arena:publish_friend:00000000-0000-0000-0000-000000000001"
        for button in buttons
    )
    assert any(button.callback_data == "menu:main" for button in buttons)


def test_friend_challenge_share_keyboard_never_includes_arena_publish_pre_baseline() -> None:
    keyboard = build_friend_challenge_share_keyboard(
        invite_link="https://t.me/quizarena_bot?start=fc_token",
        challenge_id="00000000-0000-0000-0000-000000000001",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.text for button in buttons] == [
        "📤 Teilen ->",
        "✅ Einladung gesendet",
        "⚔️ Jetzt spielen",
        "⏳ Auf Freund warten",
    ]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "arena:publish_friend:00000000-0000-0000-0000-000000000001" not in callbacks


def test_friend_challenge_share_keyboard_without_link_contains_back_only() -> None:
    keyboard = build_friend_challenge_share_keyboard(
        invite_link=None,
        challenge_id=None,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert all(button.url is None for button in buttons)
    callbacks = [button.callback_data for button in buttons]
    assert callbacks == ["home:open"]


def test_friend_challenge_start_keyboard_contains_single_cta() -> None:
    keyboard = build_friend_challenge_start_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001"
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.text for button in buttons] == ["⚔️ Jetzt spielen"]
    assert [button.callback_data for button in buttons] == [
        "friend:next:00000000-0000-0000-0000-000000000001"
    ]


def test_friend_challenge_share_confirmed_keyboard_contains_unlocked_choices() -> None:
    keyboard = build_friend_challenge_share_confirmed_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001"
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.text for button in buttons] == [
        "📤 Teilen ->",
        "✅ Einladung gesendet",
        "⚔️ Jetzt spielen",
        "⏳ Auf Freund warten",
    ]
    assert not any(button.url and "duel_" in button.url for button in buttons)
    assert [button.callback_data for button in buttons if button.callback_data] == [
        "friend:invite:sent:00000000-0000-0000-0000-000000000001",
        "friend:next:00000000-0000-0000-0000-000000000001",
        "menu:main",
    ]


def test_friend_challenge_share_url_builder_encodes_target_and_text() -> None:
    url = build_friend_challenge_share_url(
        base_link="https://t.me/quizarena_bot",
        share_text="Proof Card",
    )
    assert "https://t.me/share/url" in url
    assert "https%3A%2F%2Ft.me%2Fquizarena_bot" in url
    assert "Proof+Card" in url


def test_friend_challenge_result_share_keyboard_contains_share_and_navigation() -> None:
    keyboard = build_friend_challenge_result_share_keyboard(
        share_url="https://t.me/share/url?url=https%3A%2F%2Ft.me%2Fquizarena_bot&text=proof",
        challenge_id="00000000-0000-0000-0000-000000000001",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    inline_queries = [
        button.switch_inline_query for button in buttons if button.switch_inline_query
    ]
    assert inline_queries == ["proof:duel:00000000-0000-0000-0000-000000000001"]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "friend:rematch:00000000-0000-0000-0000-000000000001" in callbacks
    assert "home:open" in callbacks
    assert "arena:publish_friend:00000000-0000-0000-0000-000000000001" not in callbacks


def test_friend_challenge_result_share_keyboard_hides_rematch_when_rollout_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(duel_rollout, "is_canonical_duels_enabled", lambda: False)
    keyboard = build_friend_challenge_result_share_keyboard(
        share_url="https://t.me/share/url?url=https%3A%2F%2Ft.me%2Fquizarena_bot&text=proof",
        challenge_id="00000000-0000-0000-0000-000000000001",
    )
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert callbacks == ["home:open"]
