from __future__ import annotations

from app.game.questions.types import QuizQuestion

_ARTIKEL_OPTIONS = ("der", "die", "das", "kein Artikel")
_ARTIKEL_INDEX = {"der": 0, "die": 1, "das": 2}
_ARTIKEL_ITEMS: tuple[tuple[str, str, str, str], ...] = (
    ("artikel_001", "Welcher Artikel passt zu 'Apfel'?", "der", "A1"),
    ("artikel_002", "Welcher Artikel passt zu 'Lampe'?", "die", "A1"),
    ("artikel_003", "Welcher Artikel passt zu 'Brot'?", "das", "A1"),
    ("artikel_004", "Welcher Artikel passt zu 'Hund'?", "der", "A1"),
    ("artikel_005", "Welcher Artikel passt zu 'Tasche'?", "die", "A1"),
    ("artikel_006", "Welcher Artikel passt zu 'Fenster'?", "das", "A1"),
    ("artikel_007", "Welcher Artikel passt zu 'Lehrer'?", "der", "A1"),
    ("artikel_008", "Welcher Artikel passt zu 'Blume'?", "die", "A1"),
    ("artikel_009", "Welcher Artikel passt zu 'Bahnhof'?", "der", "A2"),
    ("artikel_010", "Welcher Artikel passt zu 'Zeitung'?", "die", "A2"),
    ("artikel_011", "Welcher Artikel passt zu 'Messer'?", "das", "A2"),
    ("artikel_012", "Welcher Artikel passt zu 'Kuchen'?", "der", "A2"),
    ("artikel_013", "Welcher Artikel passt zu 'Wohnung'?", "die", "A2"),
    ("artikel_014", "Welcher Artikel passt zu 'Fahrrad'?", "das", "A2"),
    ("artikel_015", "Welcher Artikel passt zu 'Flughafen'?", "der", "A2"),
    ("artikel_016", "Welcher Artikel passt zu 'Stimme'?", "die", "A2"),
    ("artikel_017", "Welcher Artikel passt zu 'Computer'?", "der", "B1"),
    ("artikel_018", "Welcher Artikel passt zu 'Gesundheit'?", "die", "B1"),
    ("artikel_019", "Welcher Artikel passt zu 'Ergebnis'?", "das", "B1"),
    ("artikel_020", "Welcher Artikel passt zu 'Rucksack'?", "der", "B1"),
    ("artikel_021", "Welcher Artikel passt zu 'Entscheidung'?", "die", "B1"),
    ("artikel_022", "Welcher Artikel passt zu 'Werkzeug'?", "das", "B1"),
    ("artikel_023", "Welcher Artikel passt zu 'Vorschlag'?", "der", "B1"),
    ("artikel_024", "Welcher Artikel passt zu 'Fortschritt'?", "der", "B2"),
    ("artikel_025", "Welcher Artikel passt zu 'Verantwortung'?", "die", "B2"),
    ("artikel_026", "Welcher Artikel passt zu 'Verhältnis'?", "das", "B2"),
    ("artikel_027", "Welcher Artikel passt zu 'Eindruck'?", "der", "B2"),
    ("artikel_028", "Welcher Artikel passt zu 'Gelegenheit'?", "die", "B2"),
    ("artikel_029", "Welcher Artikel passt zu 'Verhalten'?", "das", "B2"),
    ("artikel_030", "Welcher Artikel passt zu 'Wettbewerb'?", "der", "B2"),
)


def build_artikel_sprint_pool() -> tuple[QuizQuestion, ...]:
    return tuple(
        QuizQuestion(
            question_id=question_id,
            text=text,
            options=_ARTIKEL_OPTIONS,
            correct_option=_ARTIKEL_INDEX[article],
            level=level,
            category="Artikel",
        )
        for question_id, text, article, level in _ARTIKEL_ITEMS
    )
