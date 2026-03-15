from __future__ import annotations

from typing import Any

from app.db.models.user_events import UserEvent

from .queries import ContentHealthRows
from .sorting import _level_sort_key


def _build_level_stats(
    totals: list[tuple[Any, Any]],
    attempts: list[tuple[Any, Any]],
) -> list[dict[str, object]]:
    attempt_map = {str(level): int(total) for level, total in attempts}
    level_stats: list[dict[str, object]] = []
    for level, total in totals:
        total_count = int(total)
        answered = attempt_map.get(str(level), 0)
        coverage = round((answered / total_count) * 100, 2) if total_count > 0 else 0
        level_stats.append(
            {
                "level": str(level),
                "total_questions": total_count,
                "attempts": answered,
                "coverage_percent": coverage,
            }
        )
    return level_stats


def _build_flagged_items(flagged: list[UserEvent]) -> list[dict[str, object]]:
    return [
        {
            "id": int(item.id),
            "user_id": int(item.user_id),
            "reason": item.event_type,
            "payload": item.payload,
            "created_at": item.created_at.isoformat(),
        }
        for item in flagged
    ]


def _build_grammar_status(grammar_event: UserEvent | None) -> dict[str, object]:
    grammar_status: dict[str, object] = {
        "status": "unknown",
        "updated_at": None,
        "payload": {},
    }
    if grammar_event is not None:
        grammar_status = {
            "status": str(grammar_event.payload.get("status") or "unknown"),
            "updated_at": grammar_event.created_at.isoformat(),
            "payload": grammar_event.payload,
        }
    return grammar_status


def _build_mode_level_distribution(
    mode_level_rows: list[tuple[Any, Any, Any]],
) -> list[dict[str, object]]:
    mode_totals: dict[str, int] = {}
    total_mode_attempts = 0
    for mode_code, _, attempts_total in mode_level_rows:
        attempts_count = int(attempts_total)
        mode_key = str(mode_code)
        mode_totals[mode_key] = mode_totals.get(mode_key, 0) + attempts_count
        total_mode_attempts += attempts_count

    distribution: list[dict[str, object]] = []
    sorted_rows = sorted(
        mode_level_rows,
        key=lambda row: (str(row[0]), _level_sort_key(str(row[1]))),
    )
    for mode_code, level, attempts_total in sorted_rows:
        mode_key = str(mode_code)
        attempts_count = int(attempts_total)
        mode_total = mode_totals.get(mode_key, 0)
        distribution.append(
            {
                "mode_code": mode_key,
                "level": str(level),
                "attempts": attempts_count,
                "percent_in_mode": (
                    round((attempts_count / mode_total) * 100, 2) if mode_total > 0 else 0
                ),
                "percent_of_all_attempts": (
                    round((attempts_count / total_mode_attempts) * 100, 2)
                    if total_mode_attempts > 0
                    else 0
                ),
            }
        )
    return distribution


def build_content_health_payload(rows: ContentHealthRows) -> dict[str, object]:
    return {
        "level_stats": _build_level_stats(rows.totals, rows.attempts),
        "flagged_questions": _build_flagged_items(rows.flagged),
        "grammar_pipeline": _build_grammar_status(rows.grammar_event),
        "duplicates": [
            {"question_text": text, "count": int(count)} for text, count in rows.duplicate_rows
        ],
        "mode_level_distribution": _build_mode_level_distribution(rows.mode_level_rows),
    }
