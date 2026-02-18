from app.bot.keyboards.quiz import build_quiz_keyboard


def test_quiz_keyboard_contains_answer_callbacks_and_stop_button() -> None:
    keyboard = build_quiz_keyboard(
        session_id="00000000-0000-0000-0000-000000000001",
        options=("A", "B", "C", "D"),
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert "answer:00000000-0000-0000-0000-000000000001:0" in callbacks
    assert "answer:00000000-0000-0000-0000-000000000001:1" in callbacks
    assert "answer:00000000-0000-0000-0000-000000000001:2" in callbacks
    assert "answer:00000000-0000-0000-0000-000000000001:3" in callbacks
    assert "game:stop" in callbacks
