"""Core scanning logic for quiz bank ambiguity checks."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from quizbank_ambiguity_constants import OPTION_COLUMNS
from quizbank_ambiguity_io import read_table
from quizbank_ambiguity_text import key_family, norm, question_signature


def scan_file(path: Path) -> dict[str, Any]:
    columns, rows = read_table(path)
    if "question" not in columns:
        return {
            "file": str(path),
            "row_count": len(rows),
            "exact_duplicate_groups": [],
            "exact_conflict_groups": [],
            "signature_conflict_groups": [],
            "fuzzy_conflicts": [],
            "same_row_multi_logical_candidates": [],
        }

    question_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    signature_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    key_family_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    repeats_same_answer: list[dict[str, Any]] = []
    exact_conflicts: list[dict[str, Any]] = []
    signature_conflicts: list[dict[str, Any]] = []
    fuzzy_conflicts: list[dict[str, Any]] = []
    same_row_candidates: list[dict[str, Any]] = []

    for row in rows:
        q = norm(row.get("question"))
        if q:
            question_groups[q].append(row)
            signature_groups[question_signature(str(row.get("question") or ""))].append(row)
        if "key" in columns:
            family = key_family(row.get("key"))
            if family:
                key_family_groups[family].append(row)

        options = [norm(row.get(col)) for col in OPTION_COLUMNS if col in columns]
        if len(options) >= 2 and len(set(options)) < len(options):
            same_row_candidates.append(
                {
                    "row": int(row["_row"]),
                    "reason": "duplicate options after normalization",
                    "question": row.get("question"),
                    "options": [row.get(col) for col in OPTION_COLUMNS if col in columns],
                }
            )

    for q, group in question_groups.items():
        if len(group) < 2:
            continue
        answers = sorted({norm(g.get("correct_answer")) for g in group})
        item = {
            "question": group[0].get("question"),
            "rows": [int(g["_row"]) for g in group],
            "answers": answers,
        }
        if len(answers) == 1:
            repeats_same_answer.append(item)
        else:
            exact_conflicts.append(item)

    for sig, group in signature_groups.items():
        if len(group) < 2 or not sig:
            continue
        answers = sorted({norm(g.get("correct_answer")) for g in group})
        if len(answers) > 1:
            signature_conflicts.append(
                {
                    "signature": sig,
                    "rows": [int(g["_row"]) for g in group],
                    "questions": [g.get("question") for g in group],
                    "answers": answers,
                }
            )

    template_repeat_groups: list[dict[str, Any]] = []
    for family, group in key_family_groups.items():
        if len(group) < 2:
            continue
        answers = sorted({norm(g.get("correct_answer")) for g in group})
        template_repeat_groups.append(
            {
                "family": family,
                "size": len(group),
                "rows": [int(g["_row"]) for g in group],
                "questions": [g.get("question") for g in group][:10],
                "answers": answers,
                "answer_count": len(answers),
            }
        )
    template_repeat_groups = sorted(template_repeat_groups, key=lambda x: x["size"], reverse=True)

    q_items = [
        (int(row["_row"]), norm(row.get("question")), norm(row.get("correct_answer")))
        for row in rows
    ]
    for i, (r1, q1, a1) in enumerate(q_items):
        if not q1:
            continue
        for r2, q2, a2 in q_items[i + 1 :]:
            if not q2 or a1 == a2:
                continue
            score = fuzz.ratio(q1, q2)
            if score >= 96:
                fuzzy_conflicts.append(
                    {
                        "row_1": r1,
                        "row_2": r2,
                        "score": score,
                        "question_1": q1,
                        "question_2": q2,
                        "answer_1": a1,
                        "answer_2": a2,
                    }
                )
    fuzzy_conflicts = sorted(fuzzy_conflicts, key=lambda x: x["score"], reverse=True)[:100]

    return {
        "file": str(path),
        "row_count": len(rows),
        "exact_duplicate_groups": repeats_same_answer,
        "exact_conflict_groups": exact_conflicts,
        "signature_conflict_groups": signature_conflicts[:100],
        "fuzzy_conflicts": fuzzy_conflicts,
        "same_row_multi_logical_candidates": same_row_candidates[:100],
        "template_repeat_groups": template_repeat_groups,
    }
