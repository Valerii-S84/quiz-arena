from app.bot.keyboards.duels import (
    ArenaDuelButton,
    build_arena_accept_keyboard,
    build_arena_create_keyboard,
    build_arena_empty_keyboard,
    build_arena_expired_guard_keyboard,
    build_arena_guard_back_keyboard,
    build_arena_list_keyboard,
    build_arena_published_keyboard,
    build_arena_result_keyboard,
    build_arena_revanche_confirm_keyboard,
    build_duel_paywall_keyboard,
    build_duels_menu_keyboard,
    build_friend_duel_keyboard,
)


def _buttons(keyboard):
    return [button for row in keyboard.inline_keyboard for button in row]


def test_duels_menu_has_only_arena_friend_and_back() -> None:
    buttons = _buttons(build_duels_menu_keyboard())
    assert [button.text for button in buttons] == [
        "🏟 Offene Arena",
        "👤 Freundesduell",
        "↩️ Zurück",
    ]
    assert [button.callback_data for button in buttons] == [
        "duels:arena",
        "duels:friend",
        "home:open",
    ]


def test_duels_keyboards_do_not_offer_topic_level_or_format_selection() -> None:
    keyboards = [
        build_duels_menu_keyboard(),
        build_arena_empty_keyboard(),
        build_arena_list_keyboard(
            duels=(
                ArenaDuelButton(
                    duel_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    label="Max",
                    marker="🔥",
                ),
            )
        ),
        build_arena_accept_keyboard(duel_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        build_arena_create_keyboard(),
        build_arena_expired_guard_keyboard(),
        build_arena_guard_back_keyboard(),
        build_arena_published_keyboard(duel_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        build_arena_result_keyboard(user_won=True),
        build_arena_revanche_confirm_keyboard(
            source_attempt_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        ),
        build_duel_paywall_keyboard(paywall_context="arena_limit"),
        build_friend_duel_keyboard(),
    ]
    labels = [button.text for keyboard in keyboards for button in _buttons(keyboard)]
    blocked_terms = ("Thema", "Niveau", "Schwierigkeit", "A1", "A2", "B1", "5 Fragen", "12 Fragen")

    assert not any(term in label for term in blocked_terms for label in labels)


def test_arena_create_keyboard_uses_canonical_callbacks() -> None:
    buttons = _buttons(build_arena_create_keyboard())
    assert [button.callback_data for button in buttons] == [
        "arena:start_create",
        "arena:list",
    ]


def test_arena_guard_keyboards_match_vision() -> None:
    expired_buttons = _buttons(build_arena_expired_guard_keyboard())
    single_back_buttons = _buttons(build_arena_guard_back_keyboard())

    assert [button.text for button in expired_buttons] == [
        "🎯 Eigenes Arena-Duell erstellen",
        "🏟 Zur Arena",
    ]
    assert [button.callback_data for button in expired_buttons] == ["arena:create", "arena:list"]
    assert [button.text for button in single_back_buttons] == ["🏟 Zur Arena"]
    assert [button.callback_data for button in single_back_buttons] == ["arena:list"]


def test_arena_published_keyboard_has_one_action_and_arena_back() -> None:
    buttons = _buttons(
        build_arena_published_keyboard(duel_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    )

    assert [button.text for button in buttons] == [
        "👤 Freund herausfordern",
        "🏟 Zur Arena",
    ]
    assert [button.callback_data for button in buttons] == [
        "arena:challenge_friend:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "arena:list",
    ]


def test_friend_duel_clean_entry_uses_single_default_create_callback() -> None:
    buttons = _buttons(build_friend_duel_keyboard())
    assert [button.text for button in buttons] == [
        "⚔️ Freundesduell erstellen",
        "↩️ Zurück",
    ]
    assert [button.callback_data for button in buttons] == [
        "friend:challenge:format:direct:7",
        "duels:menu",
    ]


def test_duel_paywall_keyboard_sells_only_ticket_and_premium_week() -> None:
    buttons = _buttons(build_duel_paywall_keyboard(paywall_context="arena_limit"))

    assert [button.text for button in buttons] == [
        "🎟 Revanche-Ticket – 5⭐",
        "💎 Arena Pass 7 Tage – 29⭐",
        "↩️ Später",
    ]
    assert [button.callback_data for button in buttons] == [
        "buy:FRIEND_CHALLENGE_5:duel:arena_limit",
        "buy:PREMIUM_WEEK:duel:arena_limit",
        "arena:list",
    ]
    assert "buy:PREMIUM_3_DAYS" not in [button.callback_data for button in buttons]


def test_arena_result_win_keyboard_includes_revanche_first() -> None:
    buttons = _buttons(
        build_arena_result_keyboard(
            user_won=True,
            revanche_attempt_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        )
    )

    assert [button.text for button in buttons] == [
        "🔁 Revanche",
        "🏟 Zur Arena",
    ]
    assert [button.callback_data for button in buttons] == [
        "arena:revanche:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "arena:list",
    ]


def test_arena_close_loss_keyboard_includes_revanche_paywall_and_arena() -> None:
    buttons = _buttons(
        build_arena_result_keyboard(
            user_won=False,
            close_loss=True,
            revanche_attempt_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        )
    )

    assert [button.text for button in buttons] == [
        "🔁 Revanche",
        "🎟 Revanche-Ticket – 5⭐",
        "💎 Arena Pass 7 Tage – 29⭐",
        "🏟 Zur Arena",
    ]
    assert [button.callback_data for button in buttons] == [
        "arena:revanche:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "buy:FRIEND_CHALLENGE_5:duel:close_loss",
        "buy:PREMIUM_WEEK:duel:close_loss",
        "arena:list",
    ]


def test_arena_revanche_confirm_keyboard_uses_separate_send_callback() -> None:
    buttons = _buttons(
        build_arena_revanche_confirm_keyboard(
            source_attempt_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        )
    )

    assert [button.text for button in buttons] == ["🔁 Revanche senden", "🏟 Zur Arena"]
    assert [button.callback_data for button in buttons] == [
        "arena:revanche_send:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "arena:list",
    ]
