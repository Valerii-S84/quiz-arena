from __future__ import annotations

import random

from .pairing_elimination import (
    create_elimination_bracket,
    get_next_opponent,
    get_winner_bracket_slot,
)
from .pairing_swiss import build_swiss_pairs

__all__ = [
    "build_swiss_pairs",
    "create_elimination_bracket",
    "get_next_opponent",
    "get_winner_bracket_slot",
    "random",
]
