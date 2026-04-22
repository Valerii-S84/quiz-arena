from app.bot.keyboards.shop import build_shop_keyboard


def test_shop_keyboard_contains_products_and_back() -> None:
    keyboard = build_shop_keyboard()
    texts = [button.text for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert texts == [
        "⚡ Energie +10 | 5⭐",
        "⚔️ Duell-Ticket | 5⭐",
        "💎 Premium Starter | 29⭐",
        "💎 Premium Monat | 99⭐",
        "📺 Kanal abonnieren → volle Energie",
        "👥 Freunde einladen → Belohnung",
        "🎟️ Promo-Code eingeben",
        "⬅️ Zurück",
    ]
    assert "buy:ENERGY_10" in callbacks
    assert "buy:FRIEND_CHALLENGE_5" in callbacks
    assert "buy:PREMIUM_STARTER" in callbacks
    assert "buy:PREMIUM_MONTH" in callbacks
    assert "buy:PREMIUM_SEASON" not in callbacks
    assert "buy:PREMIUM_YEAR" not in callbacks
    assert "channel_bonus:open" in callbacks
    assert "friend:challenge:type:tournament" not in callbacks
    assert "referral:open" in callbacks
    assert "promo:open" in callbacks
    assert "home:open" in callbacks


def test_shop_keyboard_marks_channel_bonus_when_already_claimed() -> None:
    keyboard = build_shop_keyboard(channel_bonus_claimed=True)
    texts = [button.text for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert texts[4] == "✅ Kanal-Bonus bereits erhalten"
    assert "channel_bonus:open" not in callbacks
    assert "channel_bonus:claimed" in callbacks
