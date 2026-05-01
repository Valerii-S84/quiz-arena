from app.bot.keyboards.duels import (
    ArenaDuelButton,
    build_arena_accept_keyboard,
    build_arena_create_keyboard,
    build_arena_empty_keyboard,
    build_arena_list_keyboard,
    build_arena_published_keyboard,
    build_arena_result_keyboard,
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
        build_arena_published_keyboard(),
        build_arena_result_keyboard(user_won=True),
        build_duel_paywall_keyboard(),
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
    buttons = _buttons(build_duel_paywall_keyboard())

    assert [button.text for button in buttons] == [
        "🎟 Duell-Ticket – 5⭐",
        "👑 Premium-Woche – 29⭐",
        "↩️ Später",
    ]
    assert [button.callback_data for button in buttons] == [
        "buy:FRIEND_CHALLENGE_5",
        "buy:PREMIUM_WEEK",
        "arena:list",
    ]
    assert "buy:PREMIUM_3_DAYS" not in [button.callback_data for button in buttons]
