from __future__ import annotations

import pytest

from app.game.questions import runtime_bank_mode_picker
from tests.type_helpers import AsyncSessionStub


@pytest.mark.asyncio
async def test_pick_question_id_without_recent_uses_pool_ids_fast_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_pool_ids(_session, *, mode_code, preferred_levels):
        assert mode_code == "QUICK_MIX_A1A2"
        assert preferred_levels == ("A1",)
        return ("q1", "q2", "q3")

    async def fail_get_pool_candidates(*_args, **_kwargs):
        pytest.fail("empty recent ids should not materialize the full candidate pool")

    monkeypatch.setattr(runtime_bank_mode_picker, "_get_pool_ids", fake_get_pool_ids)
    monkeypatch.setattr(
        runtime_bank_mode_picker,
        "_get_pool_candidates",
        fail_get_pool_candidates,
    )

    selected = await runtime_bank_mode_picker._pick_question_id_from_pool(
        AsyncSessionStub(),
        mode_code="QUICK_MIX_A1A2",
        recent_question_ids=(),
        selection_seed="seed",
        preferred_levels=("A1",),
    )

    assert selected in {"q1", "q2", "q3"}
