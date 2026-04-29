from __future__ import annotations

import pytest

from app.game.questions.runtime_bank_mode_select import _list_active_records_by_id
from tests.game.runtime_bank_fixtures import _fake_record
from tests.type_helpers import AsyncSessionStub


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_list_active_records_by_id_uses_single_bulk_query_and_preserves_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = {
        "q1": _fake_record("q1"),
        "q2": _fake_record("q2"),
        "q3": _fake_record("q3"),
    }
    records["q2"].status = "DISABLED"
    list_by_ids_calls: list[tuple[str, ...]] = []

    async def fake_list_by_ids(session, *, question_ids):  # noqa: ANN001
        list_by_ids_calls.append(tuple(question_ids))
        return [records["q3"], records["q1"], records["q2"]]

    async def fail_get_by_id(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("Candidate metadata loading must not use per-id get_by_id calls")

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_by_ids",
        fake_list_by_ids,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.get_by_id",
        fail_get_by_id,
    )

    loaded = await _list_active_records_by_id(_Session(), ["q1", "q2", "q1", "q3"])

    assert list_by_ids_calls == [("q1", "q2", "q3")]
    assert [record.question_id for record in loaded] == ["q1", "q3"]
