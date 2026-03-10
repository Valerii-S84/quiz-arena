from __future__ import annotations

import re

_LEVEL_TOKEN_RE = re.compile(r"\b(?:A1|A2|B1|B2|C1|C2)\b", re.IGNORECASE)
_EMPTY_BRACKETS_RE = re.compile(r"\(\s*\)|\[\s*\]|\{\s*\}")
_WHITESPACE_RE = re.compile(r"\s+")
_TRIM_CHARS = " -_/|:,;()[]{}"


def sanitize_question_theme_label(category: str | None) -> str:
    raw_category = (category or "").strip()
    if not raw_category:
        return "Allgemein"

    without_levels = _LEVEL_TOKEN_RE.sub(" ", raw_category)
    without_empty_brackets = _EMPTY_BRACKETS_RE.sub(" ", without_levels)
    normalized = _WHITESPACE_RE.sub(" ", without_empty_brackets).strip(_TRIM_CHARS).strip()
    if normalized:
        return normalized
    return "Allgemein"
