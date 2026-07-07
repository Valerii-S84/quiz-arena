from __future__ import annotations

from collections import Counter
from types import SimpleNamespace
from typing import Any, cast

import pytest
from aiogram.methods import AnswerCallbackQuery, GetMe, SendMessage
from aiogram.types import Message as TelegramMessage
from aiogram.types import User as TelegramUser

from scripts import load_capacity_audit as audit


def test_latency_and_query_summaries_use_inclusive_percentiles() -> None:
    summary = audit._latency_summary([10.0, 20.0, 30.0, 40.0])
    query_summary = audit._query_summary([1.0, 3.0, 5.0])

    assert summary.count == 4
    assert summary.p50_ms == 25.0
    assert summary.p95_ms == 38.5
    assert summary.max_ms == 40.0
    assert query_summary.count == 3
    assert query_summary.total_ms == 9.0
    assert query_summary.p95_ms == 4.8


def test_query_recorder_digest_and_classification_helpers() -> None:
    recorder = audit.QueryRecorder()
    recorder.timings_ms.extend([2.0, 8.0])
    recorder._by_statement["SELECT * FROM users WHERE id = $1"] = [2.0, 8.0]
    recorder._by_step["user_lookup"] = [2.0]
    recorder._by_category["user_state"] = [8.0]
    recorder._by_user[3] = [2.0, 8.0]

    assert audit._classify_statement("select * from quiz_questions") == "question_pool"
    assert audit._compact_statement("SELECT   *\nFROM users") == "SELECT * FROM users"
    assert recorder.summary().total_ms == 10.0
    assert recorder.top_queries()[0].count == 2
    assert recorder.step_summaries()["user_lookup"].count == 1
    assert recorder.category_summaries()["user_state"].max_ms == 8.0
    assert recorder.user_sql_totals() == {3: 10.0}


def test_payload_builders_and_callback_extraction() -> None:
    message = audit._message_update(update_id=1, telegram_user_id=9, message_id=11)
    callback = audit._callback_update(
        update_id=2,
        telegram_user_id=9,
        callback_query_id="cb-1",
        data="answer:session:1",
        message_id=12,
    )
    markup = SimpleNamespace(
        inline_keyboard=[
            [SimpleNamespace(callback_data="noop")],
            [SimpleNamespace(callback_data="answer:x")],
        ]
    )
    message_payload = cast(dict[str, Any], message["message"])
    message_from = cast(dict[str, Any], message_payload["from"])
    callback_payload = cast(dict[str, Any], callback["callback_query"])

    assert message_from["language_code"] == "de"
    assert callback_payload["data"] == "answer:session:1"
    assert audit._extract_answer_callback([{"chat_id": 9, "reply_markup": markup}], 9) == "answer:x"
    with pytest.raises(RuntimeError):
        audit._extract_answer_callback([], 9)


@pytest.mark.asyncio
async def test_bot_api_stub_records_supported_methods() -> None:
    stub = audit.BotApiStub()

    me = cast(TelegramUser, await stub.dispatch(GetMe()))
    message = cast(TelegramMessage, await stub.dispatch(SendMessage(chat_id=42, text="Hallo")))
    answer = await stub.dispatch(AnswerCallbackQuery(callback_query_id="cb"))

    assert me.username == "quiz_arena_capacity_bot"
    assert message.chat.id == 42
    assert answer is True
    assert stub.calls == Counter({"GetMe": 1, "SendMessage": 1, "AnswerCallbackQuery": 1})
    assert stub.sent_messages[0]["text"] == "Hallo"


def test_safety_helpers_reject_prod_like_or_wrong_targets() -> None:
    assert audit._redact_url("postgresql://quiz:quiz@localhost/db") == (
        "postgresql://***:***@localhost/db"
    )
    assert audit._redis_db_number("redis://localhost:6379") == 0
    assert audit._redis_db_number("redis://localhost:6379/15") == 15
    assert audit._contains_production_marker("deutchquizarena") is True

    with pytest.raises(RuntimeError, match="isolated load-test database"):
        audit._assert_safe_load_database_url(
            "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test_copy"
        )
    with pytest.raises(RuntimeError, match="numeric DB path"):
        audit._redis_db_number("redis://localhost:6379/not-a-db")
    with pytest.raises(RuntimeError, match="DB 0 is forbidden"):
        audit._assert_safe_load_redis_url("redis://localhost:6379/0")
    with pytest.raises(RuntimeError, match="must use DB 15"):
        audit._assert_safe_load_redis_url("redis://localhost:6379/14")


def test_active_diagnostics_and_gate_helpers() -> None:
    diagnostics = audit.ActiveDiagnostics(
        pool_waits_ms={0: 2.0},
        db_holds_ms={0: 10.0, 1: 4.0},
        acquire_waves={0: 2},
    )
    payload = audit._build_active_diagnostics(
        diagnostics,
        user_sql_totals={0: 3.0, 1: 1.0},
        peak_db_connections=5,
        active_users=2,
    )

    assert payload["pool_wait_time"]["max_ms"] == 2.0
    assert payload["non_sql_inside_db_session"]["p50_ms"] == 5.0
    assert payload["peak_db_connections"] == 5
    assert audit._estimated_service_calls(2, flow="next_question_only") == Counter(
        {"estimated_sendMessage": 2}
    )


def test_db_pool_size_reads_pool_size_method(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_engine = SimpleNamespace(
        sync_engine=SimpleNamespace(pool=SimpleNamespace(size=lambda: 15))
    )

    monkeypatch.setattr(audit, "engine", fake_engine)

    assert audit._db_pool_size() == 15


def test_parse_flow_lists_and_gate_failures() -> None:
    assert audit._parse_int_list("1, 2,,3") == [1, 2, 3]
    assert audit._parse_active_flow_list("service,next_question_only") == [
        audit.FULL_SERVICE_FLOW,
        "next_question_only",
    ]
    with pytest.raises(ValueError, match="unknown active flow"):
        audit._parse_active_flow_list("unknown")

    result = audit.ActiveResult(
        active_users=1,
        flow="quiz_open_only",
        latency=audit.LatencySummary(count=1, p50_ms=100.0, p95_ms=1200.0, max_ms=1200.0),
        errors=0,
        query_summary=audit.QuerySummary(count=0, total_ms=0.0, p50_ms=0.0, p95_ms=0.0, max_ms=0.0),
        sql_per_user=0.0,
        wall_steps={},
        db_lock_waits_active=0,
        deadlocks_delta=0,
        outbound_calls={},
        query_steps={},
        query_categories={},
        top_queries=[],
        top_queries_by_count=[],
        attempts_created=1,
        duplicate_answer_groups=0,
        processed_updates={},
        cpu_time_ms=0.0,
        rss_mb=0.0,
    )

    assert audit.gate_failed(result, max_p95_ms=1000.0) is True
    assert audit.functional_gate_failed(result) is False
