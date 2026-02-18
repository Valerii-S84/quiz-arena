from __future__ import annotations

from datetime import date

from app.game.questions.types import QuizQuestion


def _daily_challenge_question(local_date_berlin: date) -> QuizQuestion:
    question_id = f"dc_{local_date_berlin.isoformat()}"
    return QuizQuestion(
        question_id=question_id,
        text="Daily Challenge: Was ist der richtige Artikel für 'Tisch'?",
        options=("das", "die", "der", "den"),
        correct_option=2,
    )


def get_question_for_mode(mode_code: str, *, local_date_berlin: date) -> QuizQuestion:
    if mode_code == "QUICK_MIX_A1A2":
        return QuizQuestion(
            question_id="qm_a1a2_001",
            text="Wähle den korrekten Satz:",
            options=(
                "Ich gehe heute zur Arbeit.",
                "Ich geht heute zur Arbeit.",
                "Ich gehen heute zur Arbeit.",
                "Ich gehst heute zur Arbeit.",
            ),
            correct_option=0,
        )

    if mode_code == "ARTIKEL_SPRINT":
        return QuizQuestion(
            question_id="artikel_001",
            text="Welcher Artikel passt zu 'Auto'?",
            options=("die", "das", "der", "den"),
            correct_option=1,
        )

    if mode_code == "DAILY_CHALLENGE":
        return _daily_challenge_question(local_date_berlin)

    return QuizQuestion(
        question_id="generic_001",
        text="Wähle die korrekte Antwort:",
        options=("Antwort A", "Antwort B", "Antwort C", "Antwort D"),
        correct_option=0,
    )
