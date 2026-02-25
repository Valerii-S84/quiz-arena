from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date
from typing import Sequence

from app.game.questions.types import QuizQuestion


def _daily_challenge_question(local_date_berlin: date) -> QuizQuestion:
    question_id = f"dc_{local_date_berlin.isoformat()}"
    return QuizQuestion(
        question_id=question_id,
        mode_code="DAILY_CHALLENGE",
        text="Daily Challenge: Was ist der richtige Artikel für 'Tisch'?",
        options=("das", "die", "der", "den"),
        correct_option=2,
    )


_QUICK_MIX_A1A2_POOL: tuple[QuizQuestion, ...] = (
    QuizQuestion(
        question_id="qm_a1a2_001",
        text="Wähle den korrekten Satz:",
        options=(
            "Ich gehe heute zur Arbeit.",
            "Ich geht heute zur Arbeit.",
            "Ich gehen heute zur Arbeit.",
            "Ich gehst heute zur Arbeit.",
        ),
        correct_option=0,
    ),
    QuizQuestion(
        question_id="qm_a1a2_002",
        text="Welche Form ist korrekt?",
        options=(
            "Wir lernt heute Deutsch.",
            "Wir lernen heute Deutsch.",
            "Wir lernst heute Deutsch.",
            "Wir gelernen heute Deutsch.",
        ),
        correct_option=1,
    ),
    QuizQuestion(
        question_id="qm_a1a2_003",
        text="Welcher Satz ist grammatisch richtig?",
        options=(
            "Er haben Zeit.",
            "Er hat Zeit.",
            "Er bist Zeit.",
            "Er sein Zeit.",
        ),
        correct_option=1,
    ),
    QuizQuestion(
        question_id="qm_a1a2_004",
        text="Welche Variante passt?",
        options=(
            "Heute ich spiele Fußball.",
            "Heute spiele ich Fußball.",
            "Heute spielt ich Fußball.",
            "Heute spielen ich Fußball.",
        ),
        correct_option=1,
    ),
)


_ARTIKEL_SPRINT_POOL: tuple[QuizQuestion, ...] = (
    QuizQuestion(
        question_id="artikel_001",
        text="Welcher Artikel passt zu 'Auto'?",
        options=("die", "das", "der", "den"),
        correct_option=1,
    ),
    QuizQuestion(
        question_id="artikel_002",
        text="Welcher Artikel passt zu 'Bahnhof'?",
        options=("die", "dem", "das", "der"),
        correct_option=3,
    ),
    QuizQuestion(
        question_id="artikel_003",
        text="Welcher Artikel passt zu 'Prüfung'?",
        options=("der", "die", "das", "den"),
        correct_option=1,
    ),
    QuizQuestion(
        question_id="artikel_004",
        text="Welcher Artikel passt zu 'Film'?",
        options=("das", "die", "den", "der"),
        correct_option=3,
    ),
)


_GENERIC_POOL: tuple[QuizQuestion, ...] = (
    QuizQuestion(
        question_id="generic_001",
        text="Wähle die korrekte Antwort:",
        options=("Antwort A", "Antwort B", "Antwort C", "Antwort D"),
        correct_option=0,
    ),
    QuizQuestion(
        question_id="generic_002",
        text="Wähle die beste Option:",
        options=("Option 1", "Option 2", "Option 3", "Option 4"),
        correct_option=1,
    ),
)


def _question_pool_for_mode(mode_code: str) -> tuple[QuizQuestion, ...]:
    if mode_code == "QUICK_MIX_A1A2":
        return _QUICK_MIX_A1A2_POOL
    if mode_code == "ARTIKEL_SPRINT":
        return _ARTIKEL_SPRINT_POOL
    return _GENERIC_POOL


def _with_mode(question: QuizQuestion, *, mode_code: str) -> QuizQuestion:
    if question.mode_code == mode_code:
        return question
    return replace(question, mode_code=mode_code)


def _stable_index(seed: str, size: int) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % size


def get_question_by_id(
    mode_code: str,
    *,
    question_id: str,
    local_date_berlin: date,
) -> QuizQuestion | None:
    if mode_code == "DAILY_CHALLENGE":
        question = _daily_challenge_question(local_date_berlin)
        return question if question.question_id == question_id else None

    for question in _question_pool_for_mode(mode_code):
        if question.question_id == question_id:
            return _with_mode(question, mode_code=mode_code)
    return None


def select_question_for_mode(
    mode_code: str,
    *,
    local_date_berlin: date,
    recent_question_ids: Sequence[str],
    selection_seed: str,
    preferred_level: str | None = None,
) -> QuizQuestion:
    if mode_code == "DAILY_CHALLENGE":
        return _daily_challenge_question(local_date_berlin)

    pool = _question_pool_for_mode(mode_code)
    recent_ids_set = set(recent_question_ids)
    candidates = [question for question in pool if question.question_id not in recent_ids_set]
    if not candidates:
        candidates = list(pool)

    index = _stable_index(selection_seed, len(candidates))
    return _with_mode(candidates[index], mode_code=mode_code)


def get_question_for_mode(mode_code: str, *, local_date_berlin: date) -> QuizQuestion:
    if mode_code == "DAILY_CHALLENGE":
        return _daily_challenge_question(local_date_berlin)

    return _with_mode(_question_pool_for_mode(mode_code)[0], mode_code=mode_code)
