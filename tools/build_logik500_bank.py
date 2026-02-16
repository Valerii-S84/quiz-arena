#!/usr/bin/env python3
"""Build a combined 500-item LOGIK bank from two 400-item source files."""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


SOURCE_FILES = [
    ("s1", Path("QuizBank/LOGIK_LUECKE_Denken_auf_Deutsch_Bank_400.csv")),
    ("s2", Path("QuizBank/LOGIK_LUECKE_Denken_auf_Deutsch_Bank_Season2_A2_B1_400.csv")),
]
OUTPUT_FILE = Path("QuizBank/LOGIK_LUECKE_Denken_auf_Deutsch_Bank_500.csv")
TARGET_COUNT = 500
CUE_PREFIXES = [
    "was passt logisch?",
    "was passt inhaltlich?",
    "was passt semantisch?",
    "sinnvoll ergänzen:",
    "sinnvoll ergaenzen:",
    "inhaltlich richtig:",
    "inhaltlich logisch:",
    "inhaltlich stimmig ergänzen:",
    "inhaltlich stimmig ergaenzen:",
    "logisch ergänzen:",
    "logisch ergaenzen:",
]

# We keep 479 rows after strict de-duplication and add 21 curated rows with
# rewritten stems to reach exactly 500 unique tasks.
CURATED_EXTRAS: dict[tuple[str, int], str] = {
    ("s1", 8): "Nach einer langen Schicht bin ich sehr ___.",
    ("s1", 9): "Im Januar ist der Wind oft ziemlich ___.",
    ("s1", 10): "Wenn ich starken Durst habe, trinke ich am liebsten ___.",
    ("s1", 11): "Für die Zugfahrt nach Berlin brauche ich ein ___.",
    ("s1", 12): "Ohne Verbindung kann ich die Datei nicht ___.",
    ("s1", 13): "Kurz vor der Prüfung bin ich meistens etwas ___.",
    ("s1", 22): "Nach mehreren Versuchen konnte ich das Rätsel endlich ___.",
    ("s1", 23): "Vor einem teuren Kauf sollte man Angebote gründlich ___.",
    ("s1", 24): "Wenn sich der Termin ändert, solltest du mich sofort ___.",
    ("s1", 25): "Der Ablauf ist zu kompliziert; wir müssen den Prozess ___.",
    ("s1", 26): "Die Anleitung ist missverständlich, wir sollten sie genauer ___.",
    ("s1", 27): "Wenn die Einnahmen sinken, müssen wir die Kosten ___.",
    ("s1", 28): "Der Plan klingt gut, aber ist er auch wirklich ___?",
    ("s1", 29): "Bevor wir entscheiden, sollten wir die Zahlen noch einmal ___.",
    ("s1", 88): "An der Haltestelle warte ich ___ den Bus.",
    ("s1", 90): "Ich spreche heute ___ meiner Lehrerin über die Hausaufgabe.",
    ("s1", 92): "Das kleine Kind hat Angst ___ dem großen Hund.",
    ("s1", 129): "Der Wecker ist nicht gestellt und wir müssen um sechs los. Nächster Schritt: ___.",
    ("s1", 130): "Mein Handy zeigt nur noch zwei Prozent Akku. Was ist jetzt logisch? ___.",
    ("s1", 131): "Es ist mitten in der Nacht und alle wollen schlafen. Nächster Schritt: ___.",
    ("s1", 132): "Die Tonne quillt über und morgen ist Abholung. Was ist jetzt logisch? ___.",
}


@dataclass
class Item:
    source: str
    row_num: int
    row: dict[str, str]
    family: str


def key_family(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"(?:_|-)v\d+$", "", text, flags=re.I)
    text = re.sub(r"(?:_|-)\d+$", "", text)
    return text


def normalize_text(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("‑", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text


def signature(value: str) -> str:
    text = normalize_text(value)
    changed = True
    while changed:
        changed = False
        for cue in CUE_PREFIXES:
            if text.startswith(cue + " "):
                text = text[len(cue) + 1 :].strip()
                changed = True
            elif text.startswith(cue):
                text = text[len(cue) :].strip()
                changed = True
        text = text.lstrip(":-,; ").strip()
    return text


def main() -> None:
    header = None
    all_items: list[Item] = []

    for source_name, source_path in SOURCE_FILES:
        with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if header is None:
                header = reader.fieldnames
            elif header != reader.fieldnames:
                raise ValueError(f"Column mismatch in {source_path}")

            for row_num, row in enumerate(reader, start=2):
                family = key_family(row.get("key", ""))
                all_items.append(Item(source=source_name, row_num=row_num, row=row, family=family))

    if header is None:
        raise ValueError("No input data found")

    # Family-level deduplication.
    family_map: defaultdict[str, list[Item]] = defaultdict(list)
    for item in all_items:
        family_map[item.family].append(item)

    unique_items: list[Item] = []
    for family in sorted(family_map.keys()):
        group = sorted(family_map[family], key=lambda x: (x.source, x.row_num))
        unique_items.append(group[0])

    # Step 2: strict semantic de-duplication by normalized signature.
    signature_map: defaultdict[str, list[Item]] = defaultdict(list)
    for item in unique_items:
        signature_map[signature(item.row.get("question", ""))].append(item)

    base_items: list[Item] = []
    extra_candidates: dict[tuple[str, int], Item] = {}
    duplicate_signature_groups = 0
    for _, group in signature_map.items():
        ordered = sorted(group, key=lambda x: (x.source, x.row_num))
        base_items.append(ordered[0])
        if len(ordered) > 1:
            duplicate_signature_groups += 1
            for item in ordered[1:]:
                extra_candidates[(item.source, item.row_num)] = item

    # Step 3: add 21 curated rows rewritten to unique stems.
    extras: list[Item] = []
    for marker, question in CURATED_EXTRAS.items():
        if marker not in extra_candidates:
            raise ValueError(f"Curated extra marker not found in candidates: {marker}")
        item = extra_candidates[marker]
        row_copy = dict(item.row)
        row_copy["question"] = question
        extras.append(
            Item(source=item.source, row_num=item.row_num, row=row_copy, family=item.family)
        )

    selected = base_items + extras
    if len(selected) != TARGET_COUNT:
        raise ValueError(
            f"Unexpected target size after merge: {len(selected)} (expected {TARGET_COUNT})"
        )

    # Final deterministic ordering for output.
    selected = sorted(
        selected,
        key=lambda x: (
            (x.row.get("level") or "").strip(),
            (x.row.get("category") or "").strip(),
            x.source,
            x.row_num,
        ),
    )

    out_rows = []
    for idx, item in enumerate(selected, start=1):
        row = dict(item.row)
        row["quiz_id"] = f"logik500_{idx:04d}"
        row["key"] = f"logik500_{idx:04d}_{item.family}"
        out_rows.append(row)

    # Sanity checks.
    key_set = {row["key"] for row in out_rows}
    if len(key_set) != len(out_rows):
        raise ValueError("Duplicate keys in output")

    question_set = Counter(normalize_text(row.get("question", "")) for row in out_rows)
    exact_dups = sum(1 for count in question_set.values() if count > 1)
    signature_set = Counter(signature(row.get("question", "")) for row in out_rows)
    signature_dups = sum(1 for count in signature_set.values() if count > 1)
    family_set = Counter(key_family(row.get("key", "")) for row in out_rows)
    family_dups = sum(1 for count in family_set.values() if count > 1)

    if signature_dups > 0:
        raise ValueError(f"Signature duplicates remained in output: {signature_dups}")
    if family_dups > 0:
        raise ValueError(f"Family duplicates remained in output: {family_dups}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"source_rows={len(all_items)}")
    print(f"unique_after_family_dedupe={len(unique_items)}")
    print(f"unique_after_signature_dedupe={len(base_items)}")
    print(f"duplicate_signature_groups={duplicate_signature_groups}")
    print(f"curated_extras_added={len(extras)}")
    print(f"selected_rows={len(out_rows)}")
    print(f"output={OUTPUT_FILE}")
    print(f"exact_duplicate_questions={exact_dups}")
    print(f"signature_duplicates={signature_dups}")
    print(f"family_duplicates={family_dups}")


if __name__ == "__main__":
    main()
