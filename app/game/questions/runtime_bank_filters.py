from __future__ import annotations

from collections import Counter
from typing import Sequence

from app.db.models.quiz_questions import QuizQuestion as QuizQuestionRecord
from app.game.questions.runtime_bank_seed import stable_index


def pick_from_pool(
    candidate_ids: Sequence[str],
    *,
    exclude_question_ids: Sequence[str],
    selection_seed: str,
) -> str | None:
    if not candidate_ids:
        return None
    if not exclude_question_ids:
        return candidate_ids[stable_index(selection_seed, len(candidate_ids))]

    excluded = set(exclude_question_ids)
    if len(excluded) >= len(candidate_ids):
        return None

    start_index = stable_index(selection_seed, len(candidate_ids))
    for offset in range(len(candidate_ids)):
        candidate_id = candidate_ids[(start_index + offset) % len(candidate_ids)]
        if candidate_id not in excluded:
            return candidate_id
    return None


def filter_active_records(
    all_records: Sequence[QuizQuestionRecord], *, ids: Sequence[str]
) -> list[QuizQuestionRecord]:
    by_id = {record.question_id: record for record in all_records}
    ordered: list[QuizQuestionRecord] = []
    for question_id in ids:
        record = by_id.get(question_id)
        if record is not None and record.status == "ACTIVE":
            ordered.append(record)
    return ordered


def select_least_used_by_category(
    *,
    candidate_records: Sequence[QuizQuestionRecord],
    previous_records: Sequence[QuizQuestionRecord],
    selection_seed: str,
) -> QuizQuestionRecord | None:
    if not candidate_records:
        return None

    category_counts: Counter[str] = Counter()
    for record in previous_records:
        category_counts[record.category] += 1

    min_count = min(category_counts.get(record.category, 0) for record in candidate_records)
    least_used_candidates = [
        record
        for record in candidate_records
        if category_counts.get(record.category, 0) == min_count
    ]
    least_used_candidates.sort(key=lambda record: record.question_id)
    return least_used_candidates[stable_index(selection_seed, len(least_used_candidates))]
