from __future__ import annotations

import argparse
import asyncio
import json
import resource
import statistics
import time
from collections import Counter
from collections.abc import Iterable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import redis.asyncio as redis
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.methods import AnswerCallbackQuery, GetMe, SendMessage
from aiogram.types import Message as TelegramMessage
from aiogram.types import User as TelegramUser
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, insert, select, text
from sqlalchemy.engine import make_url

from app.api.routes import telegram_webhook
from app.bot.application import build_dispatcher
from app.core.config import get_settings
from app.core.integration_db_safety import assert_safe_integration_db
from app.db.models.energy_state import EnergyState
from app.db.models.mode_progress import ModeProgress
from app.db.models.processed_updates import ProcessedUpdate
from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_questions import QuizQuestion
from app.db.models.quiz_sessions import QuizSession
from app.db.models.streak_state import StreakState
from app.db.models.users import User
from app.db.repo.entitlements_repo import entitlement_request_cache
from app.db.session import SessionLocal, engine
from app.economy.referrals.service import ReferralService
from app.game.questions.runtime_bank import clear_question_pool_cache
from app.game.sessions.service import GameSessionService, select_question_for_mode
from app.main import app
from app.services.channel_bonus import ChannelBonusService
from app.services.user_onboarding import UserOnboardingService
from app.workers.tasks import telegram_updates

MODE_CODE = "QUICK_MIX_A1A2"
SOURCE = "MENU"
BASE_USER_ID = 10_000_000
BASE_TELEGRAM_ID = 90_000_000_000
BASE_UPDATE_ID = 700_000_000
WEBHOOK_SECRET = "capacity-audit-secret"
LOAD_DATABASE_NAME = "quiz_arena_test"
LOAD_REDIS_DB = 15
LOCAL_REDIS_HOSTS = frozenset({"localhost", "127.0.0.1"})
PRODUCTION_URL_MARKERS = ("prod", "production", "deutchquizarena")
FULL_SERVICE_FLOW = "full_service_flow"
SERVICE_FLOW_ALIAS = "service"
ACTIVE_FLOW_CHOICES = (
    "quiz_open_only",
    "answer_visible_only",
    "next_question_only",
    FULL_SERVICE_FLOW,
    SERVICE_FLOW_ALIAS,
    "webhook",
)
ONE_SECOND_GATE_FLOWS = frozenset(
    {
        "quiz_open_only",
        "answer_visible_only",
        "next_question_only",
    }
)
_CURRENT_QUERY_STEP: ContextVar[str] = ContextVar(
    "capacity_audit_current_query_step",
    default="unscoped",
)
_CURRENT_STEP_RECORDER: ContextVar["StepRecorder | None"] = ContextVar(
    "capacity_audit_current_step_recorder",
    default=None,
)
_CURRENT_FLOW_USER_INDEX: ContextVar[int | None] = ContextVar(
    "capacity_audit_current_flow_user_index",
    default=None,
)
_CURRENT_ACTIVE_DIAGNOSTICS: ContextVar["ActiveDiagnostics | None"] = ContextVar(
    "capacity_audit_current_active_diagnostics",
    default=None,
)

TRUNCATE_TABLES = (
    "daily_metrics",
    "promo_audit_log",
    "admins",
    "promo_attempts",
    "promo_redemptions",
    "contact_requests",
    "referrals",
    "offers_impressions",
    "quiz_attempts",
    "daily_push_logs",
    "daily_question_sets",
    "daily_runs",
    "quiz_questions",
    "quiz_sessions",
    "friend_challenges",
    "tournament_round_scores",
    "tournament_matches",
    "tournament_participants",
    "tournaments",
    "mode_progress",
    "entitlements",
    "ledger_entries",
    "purchases",
    "processed_updates",
    "outbox_events",
    "analytics_events",
    "analytics_daily",
    "reconciliation_runs",
    "promo_codes",
    "promo_code_batches",
    "streak_state",
    "energy_state",
    "users",
)


@dataclass(slots=True)
class LatencySummary:
    count: int
    p50_ms: float
    p95_ms: float
    max_ms: float


@dataclass(slots=True)
class QuerySummary:
    count: int
    total_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float


@dataclass(slots=True)
class QueryDigest:
    statement: str
    count: int
    total_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float


@dataclass(slots=True)
class ScaleResult:
    users: int
    db_size_mb: float
    users_count_ms: float
    user_lookup_p95_ms: float
    global_best_ms: float
    public_stats_ms: float
    question_pool_warm_ms: float
    dispatcher_build_ms: float
    redis_keys: int
    rss_mb: float


@dataclass(slots=True)
class ActiveResult:
    active_users: int
    flow: str
    latency: LatencySummary
    errors: int
    query_summary: QuerySummary
    sql_per_user: float
    wall_steps: dict[str, QuerySummary]
    db_lock_waits_active: int
    deadlocks_delta: int
    outbound_calls: dict[str, int]
    query_steps: dict[str, QuerySummary]
    query_categories: dict[str, QuerySummary]
    top_queries: list[QueryDigest]
    top_queries_by_count: list[QueryDigest]
    attempts_created: int
    duplicate_answer_groups: int
    processed_updates: dict[str, int]
    cpu_time_ms: float
    rss_mb: float
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AuditReport:
    started_at: str
    database_url_redacted: str
    redis_url_redacted: str
    app_env: str
    db_pool_class: str
    registered_scales: list[ScaleResult] = field(default_factory=list)
    active_tests: list[ActiveResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PreparedFlowContext:
    started_sessions: dict[int, Any] = field(default_factory=dict)
    answered_sessions: dict[int, tuple[int, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class ActiveDiagnostics:
    pool_waits_ms: dict[int, float] = field(default_factory=dict)
    db_holds_ms: dict[int, float] = field(default_factory=dict)
    acquire_waves: dict[int, int] = field(default_factory=dict)


class QueryRecorder:
    def __init__(self) -> None:
        self.timings_ms: list[float] = []
        self._by_statement: dict[str, list[float]] = {}
        self._by_step: dict[str, list[float]] = {}
        self._by_category: dict[str, list[float]] = {}
        self._by_user: dict[int, list[float]] = {}

    def __enter__(self) -> QueryRecorder:
        event.listen(engine.sync_engine, "before_cursor_execute", self._before)
        event.listen(engine.sync_engine, "after_cursor_execute", self._after)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        event.remove(engine.sync_engine, "before_cursor_execute", self._before)
        event.remove(engine.sync_engine, "after_cursor_execute", self._after)

    def _before(self, conn, cursor, statement, parameters, context, executemany) -> None:
        del conn, cursor, statement, parameters, executemany
        context._capacity_audit_started_at = time.perf_counter()

    def _after(self, conn, cursor, statement, parameters, context, executemany) -> None:
        del conn, cursor, parameters, executemany
        started_at = getattr(context, "_capacity_audit_started_at", None)
        if started_at is not None:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            self.timings_ms.append(elapsed_ms)
            self._by_statement.setdefault(_compact_statement(statement), []).append(elapsed_ms)
            self._by_step.setdefault(_CURRENT_QUERY_STEP.get(), []).append(elapsed_ms)
            self._by_category.setdefault(_classify_statement(statement), []).append(elapsed_ms)
            user_index = _CURRENT_FLOW_USER_INDEX.get()
            if user_index is not None:
                self._by_user.setdefault(user_index, []).append(elapsed_ms)

    def summary(self) -> QuerySummary:
        return QuerySummary(
            count=len(self.timings_ms),
            total_ms=round(sum(self.timings_ms), 3),
            p50_ms=round(_percentile(self.timings_ms, 50), 3),
            p95_ms=round(_percentile(self.timings_ms, 95), 3),
            max_ms=round(max(self.timings_ms) if self.timings_ms else 0.0, 3),
        )

    def top_queries(self, *, limit: int = 10) -> list[QueryDigest]:
        return self._digest_items(
            sorted(
                self._by_statement.items(),
                key=lambda item: sum(item[1]),
                reverse=True,
            )[:limit]
        )

    def top_queries_by_count(self, *, limit: int = 10) -> list[QueryDigest]:
        return self._digest_items(
            sorted(
                self._by_statement.items(),
                key=lambda item: (len(item[1]), sum(item[1])),
                reverse=True,
            )[:limit]
        )

    def step_summaries(self) -> dict[str, QuerySummary]:
        return {step: _query_summary(timings) for step, timings in sorted(self._by_step.items())}

    def category_summaries(self) -> dict[str, QuerySummary]:
        return {
            category: _query_summary(timings)
            for category, timings in sorted(self._by_category.items())
        }

    def user_sql_totals(self) -> dict[int, float]:
        return {user_index: sum(timings) for user_index, timings in self._by_user.items()}

    @staticmethod
    def _digest_items(items: list[tuple[str, list[float]]]) -> list[QueryDigest]:
        return [
            QueryDigest(
                statement=statement,
                count=len(timings),
                total_ms=round(sum(timings), 3),
                p50_ms=round(_percentile(timings, 50), 3),
                p95_ms=round(_percentile(timings, 95), 3),
                max_ms=round(max(timings) if timings else 0.0, 3),
            )
            for statement, timings in items
        ]


def _query_summary(timings_ms: list[float]) -> QuerySummary:
    return QuerySummary(
        count=len(timings_ms),
        total_ms=round(sum(timings_ms), 3),
        p50_ms=round(_percentile(timings_ms, 50), 3),
        p95_ms=round(_percentile(timings_ms, 95), 3),
        max_ms=round(max(timings_ms) if timings_ms else 0.0, 3),
    )


class StepRecorder:
    def __init__(self) -> None:
        self._by_step: dict[str, list[float]] = {}
        self._token = None

    def __enter__(self) -> StepRecorder:
        self._token = _CURRENT_STEP_RECORDER.set(self)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            _CURRENT_STEP_RECORDER.reset(self._token)

    def record(self, step: str, elapsed_ms: float) -> None:
        self._by_step.setdefault(step, []).append(elapsed_ms)

    def summaries(self) -> dict[str, QuerySummary]:
        return {step: _query_summary(timings) for step, timings in sorted(self._by_step.items())}


class query_step:
    def __init__(self, name: str) -> None:
        self._name = name
        self._token = None
        self._started_at = 0.0

    def __enter__(self) -> None:
        self._token = _CURRENT_QUERY_STEP.set(self._name)
        self._started_at = time.perf_counter()

    def __exit__(self, exc_type, exc, tb) -> None:
        recorder = _CURRENT_STEP_RECORDER.get()
        if recorder is not None:
            recorder.record(self._name, (time.perf_counter() - self._started_at) * 1000)
        if self._token is not None:
            _CURRENT_QUERY_STEP.reset(self._token)


def _classify_statement(statement: str) -> str:
    normalized = " ".join(statement.lower().split())
    if " entitlements" in normalized:
        return "entitlement_checks"
    if " energy_state" in normalized or " ledger_entries" in normalized:
        return "energy_check_update"
    if "max(streak_state.best_streak)" in normalized:
        return "leaderboard_statistics_badges"
    if " tournament_participants" in normalized or " tournaments" in normalized:
        return "leaderboard_statistics_badges"
    if " analytics_" in normalized or " daily_metrics" in normalized:
        return "leaderboard_statistics_badges"
    if " users" in normalized:
        return "user_state"
    if " streak_state" in normalized or " mode_progress" in normalized:
        return "user_state"
    if " quiz_questions" in normalized:
        return "question_pool"
    if " quiz_attempts" in normalized:
        return "answer_callback"
    if " quiz_sessions" in normalized:
        return "quiz_session"
    if " referrals" in normalized or " offers_impressions" in normalized:
        return "post_game_prompts"
    if " processed_updates" in normalized:
        return "telegram_update_handling"
    return "other"


def _compact_statement(statement: str) -> str:
    return " ".join(statement.split())[:240]


class InProcessUpdateQueue:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task[str]] = {}

    def delay(self, *, update_payload: dict[str, object], update_id: int) -> None:
        self._tasks[update_id] = asyncio.create_task(
            telegram_updates.process_update_async(update_payload, update_id=update_id)
        )

    async def drain_update(self, update_id: int) -> str:
        task = self._tasks.pop(update_id, None)
        if task is None:
            raise RuntimeError(f"update_id={update_id} was not enqueued")
        return await task

    async def drain_all(self) -> list[str]:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        if not tasks:
            return []
        return await asyncio.gather(*tasks)


class BotApiStub:
    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        self.sent_messages: list[dict[str, object]] = []
        self._message_seq = 1_000_000

    def reset(self) -> None:
        self.calls.clear()
        self.sent_messages.clear()

    def _next_message_id(self) -> int:
        self._message_seq += 1
        return self._message_seq

    def _build_message(self, *, chat_id: int, text_value: str | None) -> TelegramMessage:
        payload: dict[str, object] = {
            "message_id": self._next_message_id(),
            "date": int(datetime.now(UTC).timestamp()),
            "chat": _private_chat_payload(chat_id),
        }
        if text_value is not None:
            payload["text"] = text_value
        return TelegramMessage.model_validate(payload)

    async def dispatch(self, method: object) -> object:
        method_name = type(method).__name__
        self.calls[method_name] += 1
        if isinstance(method, GetMe):
            return TelegramUser(
                id=777_000_001,
                is_bot=True,
                first_name="QuizArena",
                username="quiz_arena_capacity_bot",
            )
        if isinstance(method, SendMessage):
            chat_id = int(method.chat_id)
            message = self._build_message(chat_id=chat_id, text_value=method.text)
            self.sent_messages.append(
                {
                    "chat_id": chat_id,
                    "message_id": message.message_id,
                    "text": method.text,
                    "reply_markup": method.reply_markup,
                }
            )
            return message
        if isinstance(method, AnswerCallbackQuery):
            return True
        raise AssertionError(f"Unexpected Telegram API method call: {type(method)!r}")


def _redact_url(url: str) -> str:
    return url.replace("quiz:quiz@", "***:***@")


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[percentile - 1]


def _latency_summary(values: list[float]) -> LatencySummary:
    return LatencySummary(
        count=len(values),
        p50_ms=round(_percentile(values, 50), 3),
        p95_ms=round(_percentile(values, 95), 3),
        max_ms=round(max(values) if values else 0.0, 3),
    )


def _rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if value > 10_000_000:
        return round(value / (1024 * 1024), 2)
    return round(value / 1024, 2)


def _chunks(values: list[int], size: int) -> Iterable[list[int]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _telegram_user_payload(telegram_user_id: int) -> dict[str, object]:
    return {
        "id": telegram_user_id,
        "is_bot": False,
        "first_name": "Capacity",
        "username": None,
        "language_code": "de",
    }


def _private_chat_payload(telegram_user_id: int) -> dict[str, object]:
    return {
        "id": telegram_user_id,
        "type": "private",
        "first_name": "Capacity",
        "username": None,
    }


def _message_update(*, update_id: int, telegram_user_id: int, message_id: int) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "date": int(datetime.now(UTC).timestamp()),
            "chat": _private_chat_payload(telegram_user_id),
            "from": _telegram_user_payload(telegram_user_id),
            "text": "/start",
            "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
        },
    }


def _callback_update(
    *,
    update_id: int,
    telegram_user_id: int,
    callback_query_id: str,
    data: str,
    message_id: int,
) -> dict[str, object]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": callback_query_id,
            "from": _telegram_user_payload(telegram_user_id),
            "chat_instance": f"capacity-chat-{telegram_user_id}",
            "data": data,
            "message": {
                "message_id": message_id,
                "date": int(datetime.now(UTC).timestamp()),
                "chat": _private_chat_payload(telegram_user_id),
                "text": "capacity callback source",
            },
        },
    }


def _extract_answer_callback(messages: list[dict[str, object]], chat_id: int) -> str:
    for item in reversed(messages):
        if item["chat_id"] != chat_id:
            continue
        markup = item.get("reply_markup")
        rows = getattr(markup, "inline_keyboard", None)
        if not rows:
            continue
        for row in rows:
            for button in row:
                callback_data = getattr(button, "callback_data", None)
                if isinstance(callback_data, str) and callback_data.startswith("answer:"):
                    return callback_data
    raise RuntimeError(f"answer callback not found for chat_id={chat_id}")


async def _post_webhook_update(client: AsyncClient, update_payload: dict[str, object]) -> None:
    response = await client.post(
        "/webhook/telegram",
        json=update_payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
    )
    if response.status_code != 200:
        raise RuntimeError(f"webhook returned {response.status_code}: {response.text}")


def install_webhook_mocks(bot_api: BotApiStub) -> tuple[InProcessUpdateQueue, callable]:
    queue = InProcessUpdateQueue()
    original_route_get_settings = telegram_webhook.get_settings
    original_process_task = telegram_webhook.process_telegram_update
    original_build_bot = telegram_updates.build_bot
    original_bot_call = Bot.__call__

    telegram_webhook.get_settings = lambda: SimpleNamespace(
        telegram_webhook_secret=WEBHOOK_SECRET,
        telegram_webhook_enqueue_timeout_ms=250,
    )
    telegram_webhook.process_telegram_update = queue
    telegram_updates.build_bot = lambda: Bot(token="42:TEST", default=DefaultBotProperties())

    async def fake_bot_call(self: Bot, method: object, request_timeout: int | None = None):
        del self, request_timeout
        return await bot_api.dispatch(method)

    Bot.__call__ = fake_bot_call  # type: ignore[method-assign]

    def restore() -> None:
        telegram_webhook.get_settings = original_route_get_settings
        telegram_webhook.process_telegram_update = original_process_task
        telegram_updates.build_bot = original_build_bot
        Bot.__call__ = original_bot_call  # type: ignore[method-assign]

    return queue, restore


def _contains_production_marker(*values: object) -> bool:
    joined = " ".join(str(value or "").lower() for value in values)
    return any(marker in joined for marker in PRODUCTION_URL_MARKERS)


def _assert_safe_load_database_url(database_url: str) -> None:
    parsed = make_url(database_url)
    database_name = parsed.database or ""
    if database_name != LOAD_DATABASE_NAME:
        raise RuntimeError(
            "DATABASE_URL must point exactly to the isolated load-test database "
            f"{LOAD_DATABASE_NAME!r}."
        )
    if _contains_production_marker(parsed.host, parsed.database, parsed.username):
        raise RuntimeError("DATABASE_URL looks production-like; refusing destructive load setup.")
    assert_safe_integration_db(str(engine.url))


def _redis_db_number(redis_url: str) -> int:
    parsed = urlparse(redis_url)
    raw_path = parsed.path.lstrip("/")
    if not raw_path:
        return 0
    try:
        return int(raw_path.split("/", maxsplit=1)[0])
    except ValueError as exc:
        raise RuntimeError("REDIS_URL must include a numeric DB path for load tests.") from exc


def _assert_safe_load_redis_url(redis_url: str) -> None:
    parsed = urlparse(redis_url)
    host = parsed.hostname or ""
    redis_db = _redis_db_number(redis_url)
    if _contains_production_marker(parsed.hostname, parsed.username, parsed.path):
        raise RuntimeError("REDIS_URL looks production-like; refusing destructive load setup.")
    if host not in LOCAL_REDIS_HOSTS:
        raise RuntimeError("REDIS_URL for load tests must use localhost or 127.0.0.1.")
    if redis_db == 0:
        raise RuntimeError("REDIS_URL DB 0 is forbidden for destructive load tests.")
    if redis_db != LOAD_REDIS_DB:
        raise RuntimeError(f"REDIS_URL must use DB {LOAD_REDIS_DB} for load tests.")


async def assert_safe_target() -> None:
    settings = get_settings()
    if settings.app_env != "load":
        raise RuntimeError("APP_ENV must be 'load' for load_capacity_audit.")
    _assert_safe_load_database_url(settings.database_url)
    _assert_safe_load_redis_url(settings.redis_url)
    if _db_pool_class() == "NullPool":
        raise RuntimeError(
            "load_capacity_audit active stages require a pooled DB engine. "
            "APP_ENV=test uses NullPool and measures connection churn; use APP_ENV=load "
            "with an isolated test DATABASE_URL instead."
        )


def _db_pool_class() -> str:
    return type(engine.sync_engine.pool).__name__


async def truncate_test_db() -> None:
    quoted_tables = ", ".join(f"'{table_name}'" for table_name in TRUNCATE_TABLES)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename IN (" + quoted_tables + ")"
            )
        )
        existing = [str(value) for value in result.scalars().all()]

    ordered_existing = [table_name for table_name in TRUNCATE_TABLES if table_name in existing]
    if not ordered_existing:
        return
    async with engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE TABLE {', '.join(ordered_existing)} RESTART IDENTITY CASCADE")
        )


async def flush_test_redis() -> int:
    client = redis.Redis.from_url(get_settings().redis_url)
    try:
        await client.flushdb()
        return int(await client.dbsize())
    finally:
        await client.aclose()


async def seed_questions(question_count: int) -> None:
    now_utc = datetime.now(UTC)
    levels = ("A1", "A2", "B1", "B2")
    rows = [
        {
            "question_id": f"capacity-q-{idx:06d}",
            "mode_code": MODE_CODE,
            "source_file": "capacity_synthetic.csv",
            "level": levels[idx % len(levels)],
            "category": f"Capacity-{idx % 25:02d}",
            "question_text": f"Kapazitätsfrage {idx}?",
            "option_1": "der",
            "option_2": "die",
            "option_3": "das",
            "option_4": "den",
            "correct_option_id": idx % 4,
            "correct_answer": ("der", "die", "das", "den")[idx % 4],
            "explanation": "Synthetic capacity audit question.",
            "key": f"capacity-key-{idx:06d}",
            "status": "ACTIVE",
            "quick_mix_eligible": True,
            "created_at": now_utc,
            "updated_at": now_utc,
        }
        for idx in range(question_count)
    ]
    async with engine.begin() as conn:
        for chunk in _chunks(list(range(len(rows))), 5000):
            await conn.execute(insert(QuizQuestion), [rows[idx] for idx in chunk])


async def seed_users(target_count: int, *, existing_count: int) -> None:
    if target_count <= existing_count:
        return
    now_utc = datetime.now(UTC)
    local_day = date.today()
    new_indexes = list(range(existing_count, target_count))
    async with engine.begin() as conn:
        for chunk in _chunks(new_indexes, 5000):
            users = [
                {
                    "id": BASE_USER_ID + idx,
                    "telegram_user_id": BASE_TELEGRAM_ID + idx,
                    "referral_code": f"C{idx:010d}"[-11:],
                    "username": None,
                    "first_name": f"Capacity{idx}",
                    "language_code": "de",
                    "timezone": "Europe/Berlin",
                    "status": "ACTIVE",
                    "created_at": now_utc - timedelta(days=idx % 30),
                    "last_seen_at": now_utc - timedelta(minutes=idx % 1440),
                    "referral_prompt_shown_at": None,
                    "channel_bonus_claimed_at": None,
                }
                for idx in chunk
            ]
            energy = [
                {
                    "user_id": BASE_USER_ID + idx,
                    "free_energy": 10,
                    "paid_energy": 0,
                    "free_cap": 10,
                    "regen_interval_sec": 10_800,
                    "last_regen_at": now_utc,
                    "last_daily_topup_local_date": local_day,
                    "version": 0,
                    "updated_at": now_utc,
                }
                for idx in chunk
            ]
            streaks = [
                {
                    "user_id": BASE_USER_ID + idx,
                    "current_streak": idx % 7,
                    "best_streak": idx % 31,
                    "last_activity_local_date": local_day if idx % 3 == 0 else None,
                    "today_status": "PLAYED" if idx % 3 == 0 else "NO_ACTIVITY",
                    "streak_saver_tokens": 0,
                    "streak_saver_last_purchase_at": None,
                    "premium_freezes_used_week": 0,
                    "premium_freeze_week_start_local_date": None,
                    "version": 0,
                    "updated_at": now_utc,
                }
                for idx in chunk
            ]
            mode_progress = [
                {
                    "user_id": BASE_USER_ID + idx,
                    "mode_code": MODE_CODE,
                    "preferred_level": ("A1", "A2", "B1", "B2")[idx % 4],
                    "mix_step": idx % 3,
                    "correct_in_mix": idx % 2,
                    "created_at": now_utc,
                    "updated_at": now_utc,
                }
                for idx in chunk
            ]
            await conn.execute(insert(User), users)
            await conn.execute(insert(EnergyState), energy)
            await conn.execute(insert(StreakState), streaks)
            await conn.execute(insert(ModeProgress), mode_progress)


async def db_size_mb() -> float:
    async with engine.connect() as conn:
        value = await conn.scalar(text("SELECT pg_database_size(current_database())"))
    return round(float(value or 0) / (1024 * 1024), 3)


async def redis_key_count() -> int:
    client = redis.Redis.from_url(get_settings().redis_url)
    try:
        return int(await client.dbsize())
    finally:
        await client.aclose()


async def lock_snapshot() -> dict[str, int]:
    async with engine.connect() as conn:
        lock_waits = await conn.scalar(
            text(
                "SELECT COUNT(*)::int FROM pg_stat_activity "
                "WHERE wait_event_type = 'Lock' AND state = 'active'"
            )
        )
        deadlocks = await conn.scalar(
            text("SELECT COALESCE(SUM(deadlocks), 0)::bigint FROM pg_stat_database")
        )
    return {"lock_waits_active": int(lock_waits or 0), "deadlocks_total": int(deadlocks or 0)}


async def measure_registered_scale(users: int) -> ScaleResult:
    clear_question_pool_cache()

    started = time.perf_counter()
    async with SessionLocal.begin() as session:
        await session.scalar(select(func.count(User.id)))
    users_count_ms = (time.perf_counter() - started) * 1000

    lookup_times: list[float] = []
    sample_ids = [BASE_TELEGRAM_ID + idx for idx in range(0, users, max(1, users // 50))][:50]
    for telegram_user_id in sample_ids:
        started = time.perf_counter()
        async with SessionLocal.begin() as session:
            await UserOnboardingService.get_by_telegram_user_id(session, telegram_user_id)
        lookup_times.append((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    async with SessionLocal.begin() as session:
        await session.scalar(select(func.coalesce(func.max(StreakState.best_streak), 0)))
    global_best_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    async with SessionLocal.begin() as session:
        await session.scalar(select(func.count(User.id)))
        await session.scalar(select(func.count(QuizSession.id)))
        await session.scalar(select(func.count(QuizAttempt.id)))
    public_stats_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    async with SessionLocal.begin() as session:
        await select_question_for_mode(
            session,
            MODE_CODE,
            local_date_berlin=date.today(),
            recent_question_ids=(),
            selection_seed=f"scale:{users}",
            preferred_level=None,
        )
    question_pool_warm_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    build_dispatcher()
    dispatcher_build_ms = (time.perf_counter() - started) * 1000

    return ScaleResult(
        users=users,
        db_size_mb=await db_size_mb(),
        users_count_ms=round(users_count_ms, 3),
        user_lookup_p95_ms=round(_percentile(lookup_times, 95), 3),
        global_best_ms=round(global_best_ms, 3),
        public_stats_ms=round(public_stats_ms, 3),
        question_pool_warm_ms=round(question_pool_warm_ms, 3),
        dispatcher_build_ms=round(dispatcher_build_ms, 3),
        redis_keys=await redis_key_count(),
        rss_mb=_rss_mb(),
    )


def _normalize_active_flow(flow: str) -> str:
    return FULL_SERVICE_FLOW if flow == SERVICE_FLOW_ALIAS else flow


def _telegram_user_for_index(index: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=BASE_TELEGRAM_ID + index,
        username=None,
        first_name=f"Capacity{index}",
        language_code="de",
    )


@asynccontextmanager
async def measured_session(acquire_step: str):
    acquired_at = 0.0
    async with SessionLocal.begin() as session:
        acquire_started_at = time.perf_counter()
        with query_step(acquire_step):
            await session.connection()
        _record_pool_wait((time.perf_counter() - acquire_started_at) * 1000)
        acquired_at = time.perf_counter()
        try:
            yield session
        finally:
            pass
    hold_ms = (time.perf_counter() - acquired_at) * 1000
    _record_wall_step(acquire_step.removesuffix("_db_acquire") + "_db_hold", hold_ms)
    _record_db_hold(hold_ms)


def _record_wall_step(step: str, elapsed_ms: float) -> None:
    recorder = _CURRENT_STEP_RECORDER.get()
    if recorder is not None:
        recorder.record(step, elapsed_ms)


def _record_pool_wait(pool_wait_ms: float) -> None:
    diagnostics = _CURRENT_ACTIVE_DIAGNOSTICS.get()
    user_index = _CURRENT_FLOW_USER_INDEX.get()
    if diagnostics is None or user_index is None:
        return
    diagnostics.pool_waits_ms[user_index] = (
        diagnostics.pool_waits_ms.get(user_index, 0.0) + pool_wait_ms
    )
    diagnostics.acquire_waves[user_index] = diagnostics.acquire_waves.get(user_index, 0) + 1


def _record_db_hold(hold_ms: float) -> None:
    diagnostics = _CURRENT_ACTIVE_DIAGNOSTICS.get()
    user_index = _CURRENT_FLOW_USER_INDEX.get()
    if diagnostics is None or user_index is None:
        return
    diagnostics.db_holds_ms[user_index] = diagnostics.db_holds_ms.get(user_index, 0.0) + hold_ms


async def _prepare_started_session(index: int, *, idempotency_prefix: str) -> Any:
    now_utc = datetime.now(UTC)
    async with SessionLocal.begin() as session:
        return await GameSessionService.start_session(
            session,
            user_id=BASE_USER_ID + index,
            mode_code=MODE_CODE,
            source=SOURCE,
            idempotency_key=f"{idempotency_prefix}:start:{index}",
            now_utc=now_utc,
        )


async def _prepare_answered_session(index: int, *, idempotency_prefix: str) -> tuple[int, Any]:
    started = await _prepare_started_session(index, idempotency_prefix=idempotency_prefix)
    answer_now = datetime.now(UTC)
    async with SessionLocal.begin() as session:
        return await GameSessionService.submit_answer_for_telegram_user(
            session,
            telegram_user_id=BASE_TELEGRAM_ID + index,
            session_id=started.session.session_id,
            selected_option=index % 4,
            idempotency_key=f"{idempotency_prefix}:answer:{started.session.session_id}:{index}",
            now_utc=answer_now,
        )


async def prepare_active_flow_context(
    *,
    flow: str,
    start_index: int,
    active_users: int,
) -> PreparedFlowContext:
    context = PreparedFlowContext()
    if flow == "answer_visible_only":
        for index in range(start_index, start_index + active_users):
            context.started_sessions[index] = await _prepare_started_session(
                index,
                idempotency_prefix="audit:setup:answer-visible",
            )
    elif flow == "next_question_only":
        for index in range(start_index, start_index + active_users):
            context.answered_sessions[index] = await _prepare_answered_session(
                index,
                idempotency_prefix="audit:setup:next-question",
            )
    return context


def _build_answer_visible_payload(answered: Any) -> str:
    state = "correct" if answered.is_correct else "incorrect"
    return "\n".join(
        item
        for item in (
            state,
            answered.selected_answer_text,
            answered.correct_answer_text,
        )
        if item is not None
    )


def _build_question_payload(started: Any) -> tuple[str, tuple[str, ...]]:
    return (started.session.text, tuple(started.session.options))


async def quiz_open_only_flow_for_user(index: int) -> None:
    user_id = BASE_USER_ID + index
    telegram_user = _telegram_user_for_index(index)
    now_utc = datetime.now(UTC)

    async with measured_session("quiz_open_db_acquire") as session:
        with query_step("quiz_open_user_lookup"):
            resolved_user_id = await UserOnboardingService.get_existing_user_id_by_telegram_user_id(
                session,
                telegram_user.id,
            )
            if resolved_user_id is None:
                snapshot = await UserOnboardingService.ensure_home_snapshot(
                    session,
                    telegram_user=telegram_user,
                )
                user_id = int(snapshot.user_id)
            else:
                user_id = int(resolved_user_id)

        with query_step("quiz_open_start_session"):
            started = await GameSessionService.start_session(
                session,
                user_id=user_id,
                mode_code=MODE_CODE,
                source=SOURCE,
                idempotency_key=f"audit:quiz-open:start:{index}",
                now_utc=now_utc,
            )
        with query_step("quiz_open_prepare_response"):
            _build_question_payload(started)


async def answer_visible_only_flow_for_user(
    index: int,
    *,
    context: PreparedFlowContext,
) -> None:
    started = context.started_sessions[index]
    answer_now = datetime.now(UTC)
    async with measured_session("answer_visible_db_acquire") as session:
        with query_step("answer_visible_submit"):
            _, answered = await GameSessionService.submit_answer_for_telegram_user(
                session,
                telegram_user_id=BASE_TELEGRAM_ID + index,
                session_id=started.session.session_id,
                selected_option=index % 4,
                idempotency_key=f"audit:answer-visible:{started.session.session_id}:{index}",
                now_utc=answer_now,
            )
        with query_step("answer_visible_prepare_response"):
            _build_answer_visible_payload(answered)


async def next_question_only_flow_for_user(
    index: int,
    *,
    context: PreparedFlowContext,
) -> None:
    user_id, answered = context.answered_sessions[index]
    now_utc = datetime.now(UTC)
    async with measured_session("next_question_db_acquire") as session:
        with query_step("next_question_start_session"):
            started = await GameSessionService.start_session(
                session,
                user_id=user_id,
                mode_code=answered.mode_code,
                source=answered.source,
                idempotency_key=f"audit:next-question:start:{index}",
                now_utc=now_utc,
                preferred_question_level=answered.next_preferred_level,
                preferred_question_mix_step=answered.next_preferred_mix_step,
                recent_question_ids_override=(answered.question_id,),
                idempotency_prechecked=not answered.idempotent_replay,
            )
        with query_step("next_question_prepare_response"):
            _build_question_payload(started)


async def service_flow_for_user(index: int) -> None:
    user_id = BASE_USER_ID + index
    telegram_user = _telegram_user_for_index(index)
    now_utc = datetime.now(UTC)
    async with measured_session("full_service_user_lookup_db_acquire") as session:
        with query_step("start_user_lookup"):
            resolved_user_id = await UserOnboardingService.get_existing_user_id_by_telegram_user_id(
                session,
                telegram_user.id,
            )
            if resolved_user_id is None:
                snapshot = await UserOnboardingService.ensure_home_snapshot(
                    session,
                    telegram_user=telegram_user,
                )
                user_id = int(snapshot.user_id)
            else:
                user_id = int(resolved_user_id)

    async with measured_session("full_service_quiz_open_db_acquire") as session:
        with query_step("quiz_open_start_session"):
            started = await GameSessionService.start_session(
                session,
                user_id=user_id,
                mode_code=MODE_CODE,
                source=SOURCE,
                idempotency_key=f"audit:start:{index}",
                now_utc=now_utc,
            )

    answer_now = datetime.now(UTC)
    with entitlement_request_cache():
        async with measured_session("full_service_answer_db_acquire") as session:
            with query_step("answer_callback_submit"):
                user_id, answered = await GameSessionService.submit_answer_for_telegram_user(
                    session,
                    telegram_user_id=telegram_user.id,
                    session_id=started.session.session_id,
                    selected_option=index % 4,
                    idempotency_key=f"audit:answer:{started.session.session_id}:{index % 4}",
                    now_utc=answer_now,
                )
            with query_step("post_game_prompts"):
                show_bonus = await ChannelBonusService.should_show_post_game_prompt(
                    session,
                    user_id=user_id,
                    idempotent_replay=answered.idempotent_replay,
                )
                if not show_bonus:
                    await ReferralService.reserve_post_game_prompt(
                        session,
                        user_id=user_id,
                        now_utc=answer_now,
                    )

        async with measured_session("full_service_next_question_db_acquire") as session:
            with query_step("next_question_start_session"):
                await GameSessionService.start_session(
                    session,
                    user_id=user_id,
                    mode_code=answered.mode_code,
                    source=answered.source,
                    idempotency_key=f"audit:start:auto:{index}",
                    now_utc=answer_now,
                    preferred_question_level=answered.next_preferred_level,
                    preferred_question_mix_step=answered.next_preferred_mix_step,
                    recent_question_ids_override=(answered.question_id,),
                    idempotency_prechecked=not answered.idempotent_replay,
                )


async def webhook_flow_for_user(
    *,
    index: int,
    client: AsyncClient,
    queue: InProcessUpdateQueue,
    bot_api: BotApiStub,
) -> None:
    telegram_user_id = BASE_TELEGRAM_ID + index
    first_update_id = BASE_UPDATE_ID + index * 10
    await _post_webhook_update(
        client,
        _message_update(
            update_id=first_update_id,
            telegram_user_id=telegram_user_id,
            message_id=10 + index,
        ),
    )
    await queue.drain_update(first_update_id)
    await _post_webhook_update(
        client,
        _callback_update(
            update_id=first_update_id + 1,
            telegram_user_id=telegram_user_id,
            callback_query_id=f"capacity-play-{index}",
            data="play",
            message_id=20 + index,
        ),
    )
    await queue.drain_update(first_update_id + 1)
    answer_callback = _extract_answer_callback(bot_api.sent_messages, telegram_user_id)
    await _post_webhook_update(
        client,
        _callback_update(
            update_id=first_update_id + 2,
            telegram_user_id=telegram_user_id,
            callback_query_id=f"capacity-answer-{index}",
            data=answer_callback,
            message_id=30 + index,
        ),
    )
    await queue.drain_update(first_update_id + 2)


async def run_active_stage(
    active_users: int,
    *,
    flow: str,
    max_concurrency: int,
    start_index: int = 0,
    bot_api: BotApiStub | None = None,
) -> ActiveResult:
    resolved_flow = _normalize_active_flow(flow)
    prepared_context = await prepare_active_flow_context(
        flow=resolved_flow,
        start_index=start_index,
        active_users=active_users,
    )
    latencies: list[float] = []
    errors = 0
    before_locks = await lock_snapshot()
    before_attempt_id = await _max_attempt_id()
    before_update_id = await _max_processed_update_id()
    if bot_api is not None:
        bot_api.reset()

    async def run_one(index: int, client: AsyncClient | None, queue: InProcessUpdateQueue | None):
        nonlocal errors
        started_at = time.perf_counter()
        user_token = _CURRENT_FLOW_USER_INDEX.set(index)
        try:
            if resolved_flow == "webhook":
                if client is None or queue is None or bot_api is None:
                    raise RuntimeError("webhook flow is not configured")
                await webhook_flow_for_user(
                    index=index,
                    client=client,
                    queue=queue,
                    bot_api=bot_api,
                )
            elif resolved_flow == "quiz_open_only":
                await quiz_open_only_flow_for_user(index)
            elif resolved_flow == "answer_visible_only":
                await answer_visible_only_flow_for_user(index, context=prepared_context)
            elif resolved_flow == "next_question_only":
                await next_question_only_flow_for_user(index, context=prepared_context)
            else:
                await service_flow_for_user(index)
        except Exception:
            errors += 1
        finally:
            latencies.append((time.perf_counter() - started_at) * 1000)
            _CURRENT_FLOW_USER_INDEX.reset(user_token)

    semaphore = asyncio.Semaphore(max(1, min(max_concurrency, active_users)))

    async def limited(index: int, client: AsyncClient | None, queue: InProcessUpdateQueue | None):
        async with semaphore:
            await run_one(index, client, queue)

    cpu_started_at = time.process_time()
    active_diagnostics = ActiveDiagnostics()
    diagnostics_token = _CURRENT_ACTIVE_DIAGNOSTICS.set(active_diagnostics)
    pool_samples: list[int] = []
    stop_pool_sampling = asyncio.Event()
    pool_sampler = asyncio.create_task(
        _sample_checked_out_db_connections(stop_pool_sampling, pool_samples)
    )
    try:
        with QueryRecorder() as recorder, StepRecorder() as step_recorder:
            if resolved_flow == "webhook":
                if bot_api is None:
                    raise RuntimeError("bot_api is required for webhook flow")
                queue, restore = install_webhook_mocks(bot_api)
                try:
                    async with AsyncClient(
                        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
                        base_url="http://testserver",
                        timeout=30.0,
                    ) as client:
                        await asyncio.gather(
                            *(
                                limited(index, client, queue)
                                for index in range(start_index, start_index + active_users)
                            )
                        )
                finally:
                    restore()
            else:
                await asyncio.gather(
                    *(
                        limited(index, None, None)
                        for index in range(start_index, start_index + active_users)
                    )
                )
            diagnostics = _build_active_diagnostics(
                active_diagnostics,
                user_sql_totals=recorder.user_sql_totals(),
                peak_db_connections=max(pool_samples, default=0),
                active_users=active_users,
            )
    finally:
        stop_pool_sampling.set()
        await pool_sampler
        _CURRENT_ACTIVE_DIAGNOSTICS.reset(diagnostics_token)
    cpu_time_ms = (time.process_time() - cpu_started_at) * 1000

    after_locks = await lock_snapshot()
    query_summary = recorder.summary()
    return ActiveResult(
        active_users=active_users,
        flow=resolved_flow,
        latency=_latency_summary(latencies),
        errors=errors,
        query_summary=query_summary,
        sql_per_user=round(query_summary.count / max(1, active_users), 3),
        wall_steps=step_recorder.summaries(),
        db_lock_waits_active=after_locks["lock_waits_active"],
        deadlocks_delta=after_locks["deadlocks_total"] - before_locks["deadlocks_total"],
        outbound_calls=dict(
            bot_api.calls
            if bot_api is not None
            else _estimated_service_calls(active_users, flow=resolved_flow)
        ),
        query_steps=recorder.step_summaries(),
        query_categories=recorder.category_summaries(),
        top_queries=recorder.top_queries(),
        top_queries_by_count=recorder.top_queries_by_count(),
        attempts_created=await _count_attempts_after(before_attempt_id),
        duplicate_answer_groups=await _count_duplicate_answer_groups(),
        processed_updates=await _processed_update_status_counts_after(before_update_id),
        cpu_time_ms=round(cpu_time_ms, 3),
        rss_mb=_rss_mb(),
        diagnostics=diagnostics,
    )


async def _sample_checked_out_db_connections(
    stop_event: asyncio.Event,
    samples: list[int],
) -> None:
    while not stop_event.is_set():
        samples.append(_checked_out_db_connections())
        await asyncio.sleep(0.005)
    samples.append(_checked_out_db_connections())


def _checked_out_db_connections() -> int:
    checkedout = getattr(engine.sync_engine.pool, "checkedout", None)
    if callable(checkedout):
        return int(checkedout())
    return 0


def _build_active_diagnostics(
    active_diagnostics: ActiveDiagnostics,
    *,
    user_sql_totals: dict[int, float],
    peak_db_connections: int,
    active_users: int,
) -> dict[str, Any]:
    pool_waits = [active_diagnostics.pool_waits_ms.get(index, 0.0) for index in range(active_users)]
    db_holds = [active_diagnostics.db_holds_ms.get(index, 0.0) for index in range(active_users)]
    sql_totals = [user_sql_totals.get(index, 0.0) for index in range(active_users)]
    non_sql_inside = [
        max(0.0, db_hold_ms - sql_ms)
        for db_hold_ms, sql_ms in zip(db_holds, sql_totals, strict=True)
    ]
    acquire_waves = [
        float(active_diagnostics.acquire_waves.get(index, 0)) for index in range(active_users)
    ]
    return {
        "pool_wait_time": _summary_dict(pool_waits),
        "db_hold_time": _summary_dict(db_holds),
        "sql_time": _summary_dict(sql_totals),
        "non_sql_inside_db_session": _summary_dict(non_sql_inside),
        "acquire_waves_per_user": _summary_dict(acquire_waves),
        "peak_db_connections": peak_db_connections,
    }


def _summary_dict(values: list[float]) -> dict[str, float]:
    return {
        "count": float(len(values)),
        "p50_ms": round(_percentile(values, 50), 3),
        "p95_ms": round(_percentile(values, 95), 3),
        "max_ms": round(max(values) if values else 0.0, 3),
    }


def _estimated_service_calls(active_users: int, *, flow: str) -> Counter[str]:
    if flow == "quiz_open_only":
        return Counter(
            {
                "estimated_sendMessage": active_users,
                "estimated_answerCallbackQuery": active_users,
            }
        )
    if flow == "answer_visible_only":
        return Counter(
            {
                "estimated_sendMessage": active_users,
                "estimated_answerCallbackQuery": active_users,
            }
        )
    if flow == "next_question_only":
        return Counter({"estimated_sendMessage": active_users})
    return Counter(
        {
            "estimated_sendMessage": active_users * 3,
            "estimated_answerCallbackQuery": active_users * 2,
        }
    )


async def _max_attempt_id() -> int:
    async with SessionLocal.begin() as session:
        value = await session.scalar(select(func.coalesce(func.max(QuizAttempt.id), 0)))
    return int(value or 0)


async def _max_processed_update_id() -> int:
    async with SessionLocal.begin() as session:
        value = await session.scalar(select(func.coalesce(func.max(ProcessedUpdate.update_id), 0)))
    return int(value or 0)


async def _count_attempts_after(min_id: int) -> int:
    async with SessionLocal.begin() as session:
        value = await session.scalar(
            select(func.count(QuizAttempt.id)).where(QuizAttempt.id > min_id)
        )
    return int(value or 0)


async def _count_duplicate_answer_groups() -> int:
    grouped = (
        select(QuizAttempt.idempotency_key)
        .group_by(QuizAttempt.idempotency_key)
        .having(func.count(QuizAttempt.id) > 1)
        .subquery()
    )
    async with SessionLocal.begin() as session:
        value = await session.scalar(select(func.count()).select_from(grouped))
    return int(value or 0)


async def _processed_update_status_counts_after(min_update_id: int) -> dict[str, int]:
    async with SessionLocal.begin() as session:
        rows = (
            await session.execute(
                select(ProcessedUpdate.status, func.count(ProcessedUpdate.update_id))
                .where(ProcessedUpdate.update_id > min_update_id)
                .group_by(ProcessedUpdate.status)
            )
        ).all()
    return {status: int(total) for status, total in rows}


async def explain_hot_queries() -> dict[str, list[str]]:
    statements = {
        "global_best_streak": "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) "
        "SELECT COALESCE(MAX(best_streak), 0) FROM streak_state",
        "user_lookup": "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) "
        f"SELECT * FROM users WHERE telegram_user_id = {BASE_TELEGRAM_ID}",
        "recent_attempts": "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) "
        f"SELECT qa.question_id FROM quiz_attempts qa "
        f"JOIN quiz_sessions qs ON qa.session_id = qs.id "
        f"WHERE qa.user_id = {BASE_USER_ID} AND qs.mode_code = '{MODE_CODE}' "
        "ORDER BY qa.answered_at DESC LIMIT 20",
    }
    result: dict[str, list[str]] = {}
    async with engine.connect() as conn:
        for name, statement in statements.items():
            rows = (await conn.execute(text(statement))).all()
            result[name] = [str(row[0]) for row in rows]
    return result


def gate_failed(result: ActiveResult, *, max_p95_ms: float) -> bool:
    if result.errors > 0 or result.duplicate_answer_groups > 0 or result.deadlocks_delta > 0:
        return True
    return result.flow in ONE_SECOND_GATE_FLOWS and result.latency.p95_ms > max_p95_ms


def functional_gate_failed(result: ActiveResult) -> bool:
    return result.errors > 0 or result.duplicate_answer_groups > 0 or result.deadlocks_delta > 0


async def run_audit(args: argparse.Namespace) -> AuditReport:
    await assert_safe_target()
    await truncate_test_db()
    await flush_test_redis()
    await seed_questions(args.questions)

    report = AuditReport(
        started_at=datetime.now(UTC).isoformat(),
        database_url_redacted=_redact_url(str(engine.url)),
        redis_url_redacted=_redact_url(get_settings().redis_url),
        app_env=get_settings().app_env,
        db_pool_class=_db_pool_class(),
    )

    existing_users = 0
    for users in args.registered_scales:
        started_at = time.perf_counter()
        await seed_users(users, existing_count=existing_users)
        existing_users = users
        seed_ms = (time.perf_counter() - started_at) * 1000
        scale_result = await measure_registered_scale(users)
        report.registered_scales.append(scale_result)
        report.notes.append(f"seeded_registered_users={users} seed_ms={seed_ms:.3f}")

    bot_api = BotApiStub()
    active_index_offset = 0
    if args.webhook_smoke_users > 0:
        smoke = await run_active_stage(
            args.webhook_smoke_users,
            flow="webhook",
            max_concurrency=min(args.webhook_smoke_users, args.max_concurrency),
            start_index=active_index_offset,
            bot_api=bot_api,
        )
        active_index_offset += args.webhook_smoke_users
        report.active_tests.append(smoke)
        if functional_gate_failed(smoke):
            report.notes.append("Gate stopped after webhook smoke failure.")
            return report

    report.notes.append(
        "one_second_gate_flows="
        + ",".join(sorted(ONE_SECOND_GATE_FLOWS))
        + f" max_p95_ms={args.max_p95_ms:.3f}"
    )
    report.notes.append(f"informational_flows={FULL_SERVICE_FLOW}")

    for active_flow in args.active_flows:
        for active_users in args.active_users:
            result = await run_active_stage(
                active_users,
                flow=active_flow,
                max_concurrency=args.max_concurrency,
                start_index=active_index_offset,
                bot_api=bot_api if active_flow == "webhook" else None,
            )
            active_index_offset += active_users
            report.active_tests.append(result)
            if gate_failed(result, max_p95_ms=args.max_p95_ms):
                report.notes.append(
                    f"Gate failed at flow={result.flow} active_users={active_users}."
                )
                if args.stop_on_gate_failure:
                    report.notes.append("Gate stopped because stop_on_gate_failure=true.")
                    return report

    report.notes.append("explain_hot_queries=" + json.dumps(await explain_hot_queries()))
    return report


def _parse_int_list(raw_value: str) -> list[int]:
    return [int(item.strip()) for item in raw_value.split(",") if item.strip()]


def _parse_active_flow_list(raw_value: str) -> list[str]:
    flows = [item.strip() for item in raw_value.split(",") if item.strip()]
    if not flows:
        raise ValueError("active flow list must not be empty")
    invalid = [flow for flow in flows if flow not in ACTIVE_FLOW_CHOICES]
    if invalid:
        raise ValueError(
            "unknown active flow(s): "
            + ", ".join(invalid)
            + "; choices: "
            + ", ".join(ACTIVE_FLOW_CHOICES)
        )
    return [_normalize_active_flow(flow) for flow in flows]


def _json_default(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return str(value)


def _install_load_event_loop_policy() -> None:
    if get_settings().app_env != "load":
        return
    try:
        import uvloop
    except ImportError:
        return
    uvloop.install()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local synthetic capacity audit.")
    parser.add_argument("--registered-scales", default="1000,10000,100000")
    parser.add_argument("--active-users", default="100")
    parser.add_argument(
        "--active-flow",
        choices=ACTIVE_FLOW_CHOICES,
        default=None,
        help="Compatibility single-flow selector. Overrides --active-flows when set.",
    )
    parser.add_argument(
        "--active-flows",
        default="quiz_open_only,answer_visible_only,next_question_only,full_service_flow",
    )
    parser.add_argument("--webhook-smoke-users", type=int, default=0)
    parser.add_argument("--max-concurrency", type=int, default=100)
    parser.add_argument("--max-p95-ms", type=float, default=1000.0)
    parser.add_argument("--questions", type=int, default=5000)
    parser.add_argument("--output", default="reports/load_capacity_audit_latest.json")
    parser.add_argument("--stop-on-gate-failure", action="store_true")
    args = parser.parse_args()
    args.registered_scales = _parse_int_list(args.registered_scales)
    args.active_users = _parse_int_list(args.active_users)
    try:
        args.active_flows = _parse_active_flow_list(
            args.active_flow if args.active_flow is not None else args.active_flows
        )
    except ValueError as exc:
        parser.error(str(exc))

    _install_load_event_loop_policy()
    report = asyncio.run(run_audit(args))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, default=_json_default, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, default=_json_default, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
