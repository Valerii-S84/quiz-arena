from __future__ import annotations

import pytest

from app.game.duels import rollout as duel_rollout


@pytest.fixture(autouse=True)
def _enable_duels_rollout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(duel_rollout, "is_canonical_duels_enabled", lambda: True)
