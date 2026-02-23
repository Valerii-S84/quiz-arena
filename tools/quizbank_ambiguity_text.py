"""Text normalization helpers for the quiz bank ambiguity scan."""

from __future__ import annotations

import re
from typing import Any

from quizbank_ambiguity_constants import CUE_PREFIXES


def norm(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = text.replace("‑", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text


def question_signature(question: str) -> str:
    text = norm(question)
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
    text = text.replace("_____", "")
    text = text.replace("___", "")
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[\"“”„']", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def key_family(value: Any) -> str:
    text = norm(value)
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"(?:_|-)v\d+$", "", text, flags=re.I)
        text = re.sub(r"(?:_|-)\d+$", "", text)
    return text
