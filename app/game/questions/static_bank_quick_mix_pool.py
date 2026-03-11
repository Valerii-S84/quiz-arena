from __future__ import annotations

from app.game.questions.types import QuizQuestion

_QUICK_MIX_ITEMS: tuple[tuple[str, str, tuple[str, str, str, str], int, str, str], ...] = (
    ("qm_a1a2_001", "Ich ___ aus Berlin.", ("bin", "bist", "seid", "sind"), 0, "A1", "Verb_Conjugation"),
    ("qm_a1a2_002", "Du ___ heute viel Wasser trinken.", ("musst", "muss", "müssen", "musstet"), 0, "A1", "Modalverben"),
    ("qm_a1a2_003", "Ich habe ___ Zeit.", ("keine", "kein", "nicht", "nie"), 0, "A1", "Negation"),
    ("qm_a1a2_004", "Was ist der Plural von 'Tag'?", ("Tage", "Tags", "Tagen", "Tagee"), 0, "A1", "Plural_Check"),
    ("qm_a1a2_005", "___ heißt du?", ("Wie", "Wo", "Wann", "Warum"), 0, "A1", "W_Fragen"),
    ("qm_a1a2_006", "Ich wohne ___ Berlin.", ("in", "an", "auf", "bei"), 0, "A1", "Preposition_Selection"),
    ("qm_a1a2_007", "Das ist ___ Bruder.", ("mein", "meine", "meinen", "meinem"), 0, "A1", "Possessive_Adjectives"),
    ("qm_a1a2_008", "Im Klassenzimmer schreibt man mit einem ___.", ("Stift", "Teller", "Bett", "Schuh"), 0, "A1", "Topic_Vocabulary_Themes"),
    ("qm_a1a2_009", "Ich kaufe einen ___ Mantel.", ("warmen", "warme", "warmes", "warm"), 0, "A2", "Adjektivendungen"),
    ("qm_a1a2_010", "Wir ___ morgen ins Kino.", ("gehen", "geht", "gehe", "ging"), 0, "A2", "Verb_Conjugation"),
    ("qm_a1a2_011", "A: Hast du Hunger? B: Ja, ich möchte ___ essen.", ("etwas", "nie", "kein", "weg"), 0, "A2", "Mini_Dialog"),
    ("qm_a1a2_012", "Er kommt heute ___.", ("nicht", "kein", "keine", "nichts"), 0, "A2", "Negation"),
    ("qm_a1a2_013", "Was ist der Plural von 'Museum'?", ("Museen", "Museums", "Musee", "Musen"), 0, "A2", "Plural_Check"),
    ("qm_a1a2_014", "___ fängt der Kurs an? Um neun Uhr.", ("Wann", "Wie", "Wer", "Wohin"), 0, "A2", "W_Fragen"),
    ("qm_a1a2_015", "Das Bild hängt ___ der Wand.", ("an", "in", "auf", "unter"), 0, "A2", "Preposition_Selection"),
    ("qm_a1a2_016", "Sie besucht ___ Großeltern am Sonntag.", ("ihre", "ihr", "ihren", "ihres"), 0, "A2", "Possessive_Adjectives"),
    ("qm_a1a2_017", "Was ist das Gegenteil von 'laut'?", ("leise", "langsam", "leer", "tief"), 0, "B1", "Antonym"),
    ("qm_a1a2_018", "Welches Wort passt am besten zu 'beginnen'?", ("anfangen", "beenden", "sammeln", "verlieren"), 0, "B1", "Synonym_Match"),
    ("qm_a1a2_019", "Wenn ich mehr Zeit hätte, ___ ich öfter kochen.", ("würde", "werde", "wurde", "werde ich"), 0, "B1", "Lexical_Gap_Fill"),
    ("qm_a1a2_020", "Man ___ hier nicht rauchen.", ("darf", "dürfen", "durfte", "darfst"), 0, "B1", "Modalverben"),
    ("qm_a1a2_021", "Sie trägt ein ___ Kleid.", ("elegantes", "elegante", "elegantem", "eleganter"), 0, "B1", "Adjektivendungen"),
    ("qm_a1a2_022", "Für eine Reise braucht man oft einen ___.", ("Reisepass", "Fernseher", "Teppich", "Löffel"), 0, "B1", "Topic_Vocabulary_Themes"),
    ("qm_a1a2_023", "A: Warum bist du zu spät? B: ___ der Zug Verspätung hatte.", ("Weil", "Obwohl", "Damit", "Wenn"), 0, "B1", "Mini_Dialog"),
    ("qm_a1a2_024", "Er nahm den Schirm mit, ___ der Himmel noch blau war.", ("obwohl", "weil", "damit", "denn"), 0, "B2", "LOGIK_LUECKE"),
    ("qm_a1a2_025", "Welches Wort ist ein Synonym für 'schwierig'?", ("kompliziert", "locker", "ruhig", "günstig"), 0, "B2", "Synonym_Match"),
    ("qm_a1a2_026", "Was ist das Gegenteil von 'Erfolg'?", ("Misserfolg", "Fortschritt", "Gewinn", "Vorteil"), 0, "B2", "Antonym"),
    ("qm_a1a2_027", "Sie interessiert sich sehr ___ nachhaltige Architektur.", ("für", "an", "auf", "über"), 0, "B2", "Preposition_Selection"),
    ("qm_a1a2_028", "Nachdem er das Buch ___, schrieb er eine Rezension.", ("gelesen hatte", "liest", "gelesen hat", "lesen würde"), 0, "B2", "Verb_Conjugation"),
    ("qm_a1a2_029", "Keines der Angebote war passend, also entschied er sich ___.", ("dagegen", "darauf", "darin", "damit"), 0, "B2", "Negation"),
    ("qm_a1a2_030", "Wir suchen eine ___ Lösung für das Problem.", ("langfristige", "langfristigen", "langfristiges", "langfristigem"), 0, "B2", "Adjektivendungen"),
)


def build_quick_mix_pool() -> tuple[QuizQuestion, ...]:
    return tuple(
        QuizQuestion(
            question_id=question_id,
            text=text,
            options=options,
            correct_option=correct_option,
            level=level,
            category=category,
        )
        for question_id, text, options, correct_option, level, category in _QUICK_MIX_ITEMS
    )
